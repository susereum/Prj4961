##Vbox testbed manager imports
import subprocess
import shutil
import xml.etree.ElementTree as ET
import shlex
import time

#gevent imports
import gevent
import gevent.monkey
from gevent.coros import BoundedSemaphore

gevent.monkey.patch_all()

#gevent imports
from gevent.pywsgi import WSGIServer
from flask import Flask
from flask import json
from flask import render_template

####vars needed for testbed manager threads:
pathToVirtualBox = "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"
groupToVms = {}
availableState = []
notAvailableState = []
restoreState = []
vms = {}
itemsOfInterest = ["name", "groups", "vrde", "VRDEActiveConnection", "VideoMode", "vrdeproperty[TCP/Ports]", "VMState"]

#vars needed for gevent (lock)
sem = BoundedSemaphore(1)

####functions needed for testbed manager threads:
def makeAvailableToNotAvailable(vmNameList):
	#print "making notAvailable",vmNameList,"\n"
	for vmName in vmNameList:
		availableState.remove(vmName)
		notAvailableState.append(vmName)
		
def makeNotAvailableToRestoreState(vmNameList):
	#print "making notAvailableToRestore:",vmNameList,"\n"
	for vmName in vmNameList:
		notAvailableState.remove(vmName)
		restoreState.append(vmName)
		
def makeRestoreToAvailableState(): #will look at restore buffer and process any items that exist
	global vms
	global groupToVms
	while True:
		#print "making restoreToAvailable:",vmNameList,"\n"
		for vmName in restoreState:
	#VBoxManage.exe controlvm victimBO_WindowsXP_SP0 poweroff
	#VBoxManage.exe snapshot victimBO_WindowsXP_SP0 restorecurrent
	#VBoxManage.exe startvm victimBO_WindowsXP_SP0 --type headless
		#Need to reload all vms that are in the group of the vm in the "restore" state
			groupToRestore = vms[vmName]["groups"]
			for vmNameToRestore in groupToVms[groupToRestore]:						
				#TODO: might replace this with a call to a shell script for timing reasons
				output = subprocess.call([pathToVirtualBox, "controlvm", vmNameToRestore, "poweroff"])
				time.sleep(1)
				output = subprocess.call([pathToVirtualBox, "snapshot", vmNameToRestore, "restorecurrent"])
				time.sleep(1)
				output = subprocess.call([pathToVirtualBox, "startvm", vmNameToRestore, "--type", "headless"])
				time.sleep(1)
				#remove from any other state lists
				if vmNameToRestore in restoreState:
					restoreState.remove(vmNameToRestore)
				if vmNameToRestore in notAvailableState:
					notAvailableState.remove(vmNameToRestore)
		time.sleep(0.1)
		
def makeNewToAvailableState(vmNameList):
	#print "making available:",vmNameList,"\n"
	for vmName in vmNameList:
		availableState.append(vmName)

def changeVideoMode(vmNameList):
	for vmName in vmNameList:
#VBoxManage.exe controlvm victimBO_WindowsXP_SP0 setvideomodehint 1024 768 16
		output = subprocess.call([pathToVirtualBox, "controlvm", vmName, "setvideomodehint","0","0","16"])

def manageStates():
	global vms
	global groupToVms
	
	while True:
		currvms = {}
		currGroupToVms = {}
		showVmInfo = ""
		
		#clear out known availableStates
		#availableState = []
		
		#first get all vms
		getVMsCmd = [pathToVirtualBox, "list", "vms"]
		vmList = subprocess.check_output(getVMsCmd).split("\n")
		
		#for each vm get info and place in state list
		for vm in vmList:
			line = vm.split("\"")
			if len(line) > 2:
				vmName = line[1]
				#print vmName
				showVmInfo = subprocess.check_output([pathToVirtualBox, "showvminfo", vmName, "--machinereadable"])
				splitVmInfo = {}
				for line in showVmInfo.split("\n"):
					keyValue=line.rstrip().split("=")
					if keyValue[0] in itemsOfInterest:
						splitVmInfo[keyValue[0]] = keyValue[1]
				
			#parse out values of interest
				
				#Only keep vms that are in a group
				if splitVmInfo["groups"] != "\"/\"" and splitVmInfo["VMState"] == "\"running\"":
					#add it to the dictionary of known vms
					currvms[vmName] = splitVmInfo
					#keep track of groups
					#need to buffer this too! 
					if splitVmInfo["groups"] not in currGroupToVms:
						currGroupToVms[splitVmInfo["groups"]] = []
					currGroupToVms[splitVmInfo["groups"]].append(vmName)
		#so we get all at once (may have to create a lock?)
		vms = currvms
		groupToVms = currGroupToVms
		#print "VMS:",vms
		print "GROUPS:",groupToVms
		########Assign each vm into a state list############
			
			#first look at any "not available" to see if they go into the "restore" state
		nasList = []
		#resList = []
		for vmName in vms:		
			if "VRDEActiveConnection" in vms[vmName]:
				if vms[vmName]["VRDEActiveConnection"] == "\"on\"" and vmName in availableState and vmName not in notAvailableState and vmName not in restoreState:
					nasList.append(vmName)
				elif vms[vmName]["VRDEActiveConnection"] == "\"off\"" and vmName in notAvailableState and vmName not in restoreState and vmName not in restoreState:
					restoreState.append(vmName)
		#makeNotAvailableToRestoreState(resList)
		makeAvailableToNotAvailable(nasList)
			#next look at restore state and make them available
		#makeRestoreToAvailableState(restoreState) #called automatically with separate thread
			
			#place any left into the available list
	
		av = []
		for vmName in vms:
			if "vrde" in vms[vmName] and vms[vmName]["vrde"] == "\"on\"":
				#make available
				if vmName not in notAvailableState and vmName not in restoreState and vmName not in availableState:
					av.append(vmName)
		makeNewToAvailableState(av)
	
		########Change video mode to 16-bit colors to reduce bandwidth###########
		vidmod = []
		for vmName in vms:
			if "VideoMode" in vms[vmName]:
				currMode = vms[vmName]["VideoMode"].split(",")[2].split("\"")[0]
				if int(currMode) > 16:
					vidmod.append(vmName)
		changeVideoMode(vidmod)
		
		print "\n\n\n"
		print "status:"
		print "available:",availableState
		print "notAvailable:",notAvailableState
		print "restore:",restoreState
		
		time.sleep(.1)

app = Flask(__name__)
app.debug = True

# Simple catch-all server
@app.route('/', defaults={'path': ''}, methods=['GET', 'POST'])
@app.route('/<path:path>', methods=['GET', 'POST'])
def catch_all(path):
    return render_template('show_data.html', templateAvailable=availableInfo

if __name__ == '__main__':
    http_server = WSGIServer(('', 4430), app)
    srv_greenlet = gevent.spawn(http_server.start)
    
    stateAssignmentThread = gevent.spawn(manageStates)
    restoreThread = gevent.spawn(makeRestoreToAvailableState)
    
    stateAssignmentThread.start()   
    restoreThread.start()
    
    try:
        gevent.joinall([srv_greenlet, stateAssignmentThread, restoreThread])
    except KeyboardInterrupt:
        print "Exiting"

#!/usr/bin/env python

import sys
import socket
from ReplicaServer import ReplicaServer

def isInteger(str):
	try:
		int(str)
		return True
	except ValueError:
		return False

# Main routine for replica server
def main():
	numberOfArgs = len(sys.argv)
	
	if (numberOfArgs != 4):
		print("Usage: ./replica <replica-name> <port-number> <repicas.txt>")
		sys.exit(1)

	replicaName = sys.argv[1]

	# Port number must be an integer
	if (not isInteger(sys.argv[2])):
		print("<port-number> must be an integer")
		print("Usage: ./replica <replica-name> <port-number> <repicas.txt>")
		sys.exit(1)

	portNumber = int(sys.argv[2])
	ipAddress = socket.gethostbyname(socket.gethostname())
	print("IP Address: " + ipAddress)
	print("Port Number:", portNumber)

	# Open <replicas.txt>
	try:
		replicaFile = open(sys.argv[3])
	except Exception as e:
		print("Caught Exception while opening the input file")
		print("Exception: ", e)	

	replicaServer = ReplicaServer(ipAddress, portNumber, replicaName, replicaFile)

main()

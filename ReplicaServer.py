#!/usr/bin/env python

import keyStore_pb2

import errno
import os.path
import sys
import socket
import threading				# Used to create threads
from datetime import datetime

sys.path.append('/home/vchaska1/protobuf/protobuf-3.5.1/python')

# Class used to represent a thread that will listen for incoming messages on a 
# given socket (otherSocket) for the given replica (replica)
class ListenerThread (threading.Thread) :
	def __init__(self, replica, otherSocket, run_event):
		threading.Thread.__init__(self)
		self.otherSocket = otherSocket
		self.replica = replica
		self.run_event = run_event

	def run(self):
		print "Running a new thread"
		try:
			self.replica.receiveMessages(self.otherSocket, self.run_event)
		except KeyboardInterrupt:
			print "Receiving KeyboardInterrupt"
			exit(1)

class ReplicaServer:

	'''
	Attributes:
		- dictionary dataDictionary
			- Dictionary holding actual (key, value) pairs at this replica. The keys
			  are ints from 0 (inclusive) to 255 (inclusive). Values are arrays of 2
			  elements where first element is the string stored at this key and the
			  second element is a datetime object representing the timestamp for the
			  last time this element was written
		- string ipAddress
			- IP Address of the machine that this ReplicaServer runs on
		- int portNumber
			- Port Number that this ReplicaServer is listening for incoming TCP
			  requests on 
		- string replicaName
			- Unique name of this ReplicaServer
		- bool isReadRepair
			- True if using Read Repair. False if using Hinted Handoff
		- dictionary replicaPorts
			- Dictionary holding 3 (replicaName, port) pairs where port is an open 
			  TCP port for communication from this ReplicaServer to the ReplicaServer
			  whose <replicaName> is replicaName. 
		- socket socket	
			- Socket of this branch that is listening for incoming TCP 
			  connection requests
		- Threading.Event run_event
			- Event object used to by the main thread to notify the other threads
			  that they need to gracefully exit
		- array of ListenerThread objects threads
			- Array of all of the ListenerThread objects that are created
		- array of String replicaNames
			- Array of the 4 unique replica names in the system
		- string WALFileName
			- name of write-ahead log file
	'''

	def __init__(self, ipAddress, portNumber, replicaName, replicaFile):
		self.ipAddress = ipAddress
		self.portNumber = portNumber
		self.replicaName = replicaName
		self.dataDictionary = {}
		self.replicaPorts = {}		
		self.run_event = threading.Event()
		self.run_event.set()
		self.threads = []
		self.replicaNames = []
		self.WALFileName = replicaName + "-wal.txt"

		# Set up the TCP socket that this branch will listen to TCP 
		# connection requests on
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		self.socket.bind((self.ipAddress, self.portNumber))
		self.socket.listen(5)

		self.processInputFile(replicaFile)

		# We loop and accept 3 connections (1 for each of the other replicas in the
		# system). Then, we need to create a thread that will listen for incoming 
		# messages on that socket
		# TODO : Commented this out to see if it's necessary
		'''i = 1
		while (i < 4):
			# Accept a connection from another replica. Create a ListenerThread to 
			# listen to that replica
			(otherSocket, address) = self.socket.accept()
			try :
				listenerThread = ListenerThread(self, otherSocket, self.run_event)
				self.threads.append(listenerThread)
				listenerThread.start()
			except Exception as e:
				print "Couldn't create a new ListenerThread"
				print e
				sys.exit(1)	
			i = i + 1
		'''
	
		# if WAL exists upon replica startup, then populate
                # the dataDictionary with the keys and values in the WAL file
		if (os.path.isfile(self.WALFileName)):
                        f = open(self.WALFileName, "r")
                        # returns a list of strings line-by-line
                        fList = f.readlines()
                        # FOR iterates through list and adds each key and
                        # value to the dataDictionary
                        for line in fList:
                                newKey = int(line.split()[0])      
                                newValue = line.split()[1]
                                newTimeStamp = str(line.split()[2] + " " + line.split()[3])
                                formattedTimeStamp = datetime.strptime( \
                                                            newTimeStamp, '%Y-%m-%d %H:%M:%S.%f')
                                self.dataDictionary[newKey] = [newValue, formattedTimeStamp]
                        
                        f.close()

		try:
			while True:
				# Accept a TCP connection request from a client (or, a down server
				# that is coming back up)
				# TODO : How do we know if it's a new server of a new client
				(clientSocket, address) = self.socket.accept()

				# Create a new ListenerThread that will receive messages from the
				# client
				listenerThread = ListenerThread(self, clientSocket, self.run_event)
				self.threads.append(listenerThread)
				listenerThread.start()

		except KeyboardInterrupt:
			self.run_event.clear()
			#  Send coodinatorExceptionMessage with errorMessage = "Aborting"
			#  to the 3 other replicas so that they send a message back and all of
			#  the listenerThreads of this process will be able to exit
			for replicaID in self.replicaPorts.keys():
				port = self.replicaPorts[replicaID]
				abortMessage = keyStore_pb2.ReplicaMessage()
				abortMessage.coordinator_exception.errorMessage = "Abort"
				abortMessage.src_replicaID = self.replicaName
				abortMessage.dst_replicaID = replicaID
				port.sendall(abortMessage.SerializeToString())
				
				port.close()
			print "Attempting to join " + str(len(self.threads)) + " threads"
			i = 0
			for listenerThread in self.threads:
				if (listenerThread.isAlive()):
					listenerThread.join()
					i = i + 1
			self.socket.shutdown(socket.SHUT_RDWR)
			self.socket.close()
			print "All threads successfully ended. Joined " + str(i) + " threads"
			sys.exit(1)

	def processInputFile(self, replicaFile):
		# Iterate through replicaFile and open TCP connection with the 3
		# other replicas
		for line in replicaFile:
			words = line.split()
			
			# Final line in file is only 2 words
			if (len(words) == 2):
				if (line == "Read Repair\n"):
					self.isReadRepair = True
				elif (line == "Hinted Handoff\n"):
					self.isReadRepair = False
				else:
					print("Error1: <replicas.txt> is formatted incorrectly")
					print(line)
					print("Usage: ./replica <replica-name> <port-number>" + \
							 " <repicas.txt>")
					sys.exit(1)
					
			# First 4 lines of the file have 3 words each
			elif (len(words) == 3):

				# Add unique relica name to self.replicaNames
				self.replicaNames.append(words[0])

				# Establish a TCP connection with all ReplicaServers except this one
				if (words[1] != self.ipAddress or int(words[2]) != self.portNumber):

					# Make sure replicaName is unique
					if (words[0] == self.replicaName):
						print("Error2: Replica names must all be unique")
						print("Usage: ./replica <replica-name> <port-number>" + \
							 " <repicas.txt>")
						sys.exit(1)
									
					# Create TCP socket (need to do a loop to account for the time
					# that it takes for other replicas to get started)
					#while True:
					try:
						sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
						sock.connect((words[1], int(words[2])))
						# TODO : Added message sending here to tell the other 
						# replicas that this is in fact a replica and not a new
						# client
						replicaMessage = keyStore_pb2.ReplicaMessage()
						replicaMessage.src_replicaID = self.replicaName
						replicaMessage.dst_replicaID = words[0]
						replicaMessage.replica_init_message.ipAddress = \
									self.ipAddress
						replicaMessage.replica_init_message.portNumber = \
									self.portNumber
						sock.sendall(replicaMessage.SerializeToString())
 						print("Connected to replica " + words[0] + \
								" with IP address " + words[1] + \
								" and port number " + words[2])
					except:
						continue
					

					# Store open socket in replicaPorts (unless there already is 
					# and entry in replicaPorts with the given replicaName
					if (words[0] in self.replicaPorts):
						print("Error3: Replica names must all be unique")
						print("Usage: ./replica <replica-name> <port-number>" + \
							 " <repicas.txt>")
						sys.exit(1)
					else:
						self.replicaPorts[words[0]] = sock


			# No lines in the file should have a word length different than 2 and 3
			else:
				print("Error4: <replicas.txt> is formatted incorrectly")
				print("Usage: ./replica <replica-name> <port-number> <repicas.txt>")
				sys.exit(1)
		

	# This function will loop indefinitely and receive incoming messages on the given
	# socket.
	def receiveMessages(self, sock, run_event):
		receivedMessage = keyStore_pb2.ReplicaMessage()
		while run_event.is_set():
			if (sock == self.socket):
				continue
			try:
				newMessage = sock.recv(1024)
			except socket.error as e:
				if (e.errno != errno.ECONNRESET):
					raise e
				return
				
			# If sock.recv() returns "", then sock has been closed or there's been 
			# an error. So, remove the sock from self.replicaPorts and end this 
			# thread
			if (newMessage == ""):
				for replicaID in self.replicaPorts.keys():
					if (self.replicaPorts[replicaID] == sock):
						print("Closing port from this replica to " + replicaID)
						sock.shutdown(socket.SHUT_RDWR)
						sock.close()
						self.replicaPorts.pop(replicaID)
				return

			receivedMessage.ParseFromString(newMessage)
			typeOfMessage = receivedMessage.WhichOneof("replica_message")


			if (typeOfMessage == "get_request"):
				self.process_getRequestClient(sock, receivedMessage)

			elif (typeOfMessage == "put_request"):
				self.process_putRequestClient(sock, receivedMessage)

			elif (typeOfMessage == "coordinator_response"):
				self.process_coordinatorResponseMessage(sock, receivedMessage)

			elif (typeOfMessage == "coordinator_exception"):
				val = self.process_coordinatorExceptionMessage(sock, receivedMessage)
				if (val == -1):
					print("Ending a thread")
					break

			elif (typeOfMessage == "get_message"):
				self.process_getMessage(sock, receivedMessage)

			elif (typeOfMessage == "put_message"):
				self.process_putMessage(sock, receivedMessage)

			elif (typeOfMessage == "return_put_message"):
				self.process_returnPutMessage(sock, receivedMessage)
				
			elif (typeOfMessage == "return_get_message"):
				self.process_returnGetMessage(sock, receivedMessage)

			elif (typeOfMessage == "replica_init_message"):
				self.process_replicaInitMessage(sock, receivedMessage)

			else:
				print("Received message of unknown type")
			continue

	def process_getRequestClient(self, sock, message):
		print("Received getRequestClient message")

		key = message.get_request.key
		consistencyLevel = message.get_request.consistencyLevel

		quorum = self.getQuorum(key)
		valueTimestampArr = []

		if (self.replicaName in quorum):

			# Determine how many replica responses we need to wait for
			if (consistencyLevel == "quorum"):
				numWaitingOn = 1
			elif (consistencyLevel == "one"):
				numWaitingOn = 0
			else:
				print("Error: Consistency level isn't \'quorum\' or \'one\'")
				sys.exit(1)

			if (key in self.dataDictionary.keys()):
				storedValue = self.dataDictionary[key][0]
				storedTimestamp = self.dataDictionary[key][1]
			else:
				storedValue = ""
				storedTimestamp = datetime.min

			valueTimestampArr.append([storedValue, storedTimestamp])

		# Else (self.replicaName isn't in quorum)
		else:
			# Determine how many replica responses we need to wait for
			if (consistencyLevel == "quorum"):
				numWaitingOn = 2
			elif (consistencyLevel == "one"):
				numWaitingOn = 1
			else:
				print("Error: Consistency level isn't \'quorum\' or \'one\'")
				sys.exit(1)
		
		# If this replica is in quorum and consistency level is one, then immediately
		# respond to the client before contacting the rest of the quorum
		if (numWaitingOn == 0):
			responseToClient = keyStore_pb2.ReplicaMessage()
			if (storedTimestamp == datetime.min):
				responseToClient.coordinator_exception.errorMessage = \
					"Key " + str(key) + " isn't stored"
			else:
				responseToClient.coordinator_response.value = storedValue
			sock.sendall(responseToClient.SerializeToString())
		

		# Send reads to the other replicas in the quorum (but not to this one)
		for replicaID in quorum:
			if (not (replicaID in self.replicaPorts.keys())):
				continue
			if (replicaID != self.replicaName):
				getMessage = keyStore_pb2.ReplicaMessage()
				getMessage.src_replicaID = self.replicaName
				getMessage.dst_replicaID = replicaID
				getMessage.get_message.key = key
				self.replicaPorts[replicaID].sendall(getMessage.SerializeToString())

		# Get responses from replicas in the quorum
		for replicaID in quorum:
			if (not (replicaID in self.replicaPorts.keys())):
				continue

			# Only wait for messages from replicas different than this one
			if (replicaID != self.replicaName):
				port = self.replicaPorts[replicaID]
				port.settimeout(2.0)
				try:
					msg = port.recv(1024)
					returnedMessage = keyStore_pb2.ReplicaMessage()
					returnedMessage.ParseFromString(msg)
					typeOfReturnedMessage = returnedMessage.WhichOneof(\
															"replica_message")
					if (typeOfReturnedMessage != "return_get_message"):
						print("Error: Unsupported type of return message")
						sys.exit(1)
					returnedValue = returnedMessage.return_get_message.value
					try:
						returnedTimestamp = datetime.strptime(                  \
								returnedMessage.return_get_message.timestamp, 	\
						 		'%Y-%m-%d %H:%M:%S.%f')
					except ValueError:
						returnedTimestamp = datetime.strptime(					\
							'0001-01-01 00:00:00.0', '%Y-%m-%d %H:%M:%S.%f')

					valueTimestampArr.append([returnedValue, returnedTimestamp])
					
					# If numWaitingOn == 1 (and we're about to decrement to 0), then 
					# we can return message to the Client
					if (numWaitingOn == 1):
						returnValue = self.getLatestValue(valueTimestampArr)
						responseToClient = keyStore_pb2.ReplicaMessage()
						if (returnValue == -1):
							responseToClient.coordinator_exception.errorMessage = \
								"Key " + str(key) + " isn't stored"
						else:	
							responseToClient.coordinator_response.value = returnValue
						sock.sendall(responseToClient.SerializeToString())

					numWaitingOn = numWaitingOn - 1

				except socket.timeout:
					print("Didn't receive a response message form replicaID: " +\
									replicaID)

				# Whether you received a response back or not, set the port back to 
				# non-blocking (timeout == 0)
				finally:
					port.settimeout(0)

		if (numWaitingOn > 0):
			print("Error: Did not receive enough responses from other replicas" \
					+ " in the quorum")
			# Send exception message back to Client
			responseToClient = keyStore_pb2.ReplicaMessage()
			responseToClient.coordinator_exception.errorMessage = "Key " + \
					str(key) + " cannot be retreived because the consistency " +\
					"level wasn't satisfied"
			sock.sendall(responseToClient.SerializeToString())

		# TODO : Need to check if this system is doing RR or HH
		if (self.isReadRepair):
			print "Doing read repair"
			self.doReadRepair(valueTimestampArr, quorum, key)
		else:
			print "Not doing read repair"

	# Perform read repair by just getting the most recent value and broadcasting it
	# to all replicas in the quorum
	def doReadRepair(self, array, quorum, key):
		value = self.getLatestValue(array)
		ts = self.getLatestTimestamp(array)

		# If getLatestValue(array) returns -1, then no replicas in the quorum have
		# the key stored. So there's no read repair to do
		if (value == -1):
			return
		
		# Send putMessage (Replica -> Replica message) to all replicas in the quorum 
		# with the latest value
		for replicaID in quorum:
			if (not (replicaID in self.replicaPorts.keys())):
				continue

			if (replicaID != self.replicaName):
				port = self.replicaPorts[replicaID]
				putMessage = keyStore_pb2.ReplicaMessage()
				putMessage.src_replicaID = self.replicaName
				putMessage.dst_replicaID = replicaID
				putMessage.put_message.key = key
				putMessage.put_message.value = value
				putMessage.put_message.timestamp = str(ts)
				port.sendall(putMessage.SerializeToString())
		# TODO : Do we need to wait for responses??
			

	def process_putRequestClient(self, sock, message):
		print("Received putRequestClient message")

		# Get timestamp
		ts = datetime.now()
		key = message.put_request.key
		value = message.put_request.value
		consistencyLevel = message.put_request.consistencyLevel
		
		quorum = self.getQuorum(key)

		if (self.replicaName in quorum):

			# Determine how many replica responses we need to wait for
			if (consistencyLevel == "quorum"):
				numWaitingOn = 1
			elif (consistencyLevel == "one"):
				numWaitingOn = 0
			else:
				print("Error: Consistency level isn't \'quorum\' or \'one\'")
				sys.exit(1)

			if (key in self.dataDictionary.keys()):
				arr = self.dataDictionary[key]
				# If the current time is greater than or equal to the stored ts, 
				# then update memory. Otherwise, do nothing
				if (ts > arr[1]):
					self.updateWAL(key, value,ts)
					self.dataDictionary[key] = [value, ts]

			# Else, (key isn't in self.dataDictionary.keys())
			else:
				self.updateWAL(key, value,ts)
				self.dataDictionary[key] = [value, ts]

		# Else (self.replicaName isn't in quorum)
		else:
			# Determine how many replica responses we need to wait for
			if (consistencyLevel == "quorum"):
				numWaitingOn = 2
			elif (consistencyLevel == "one"):
				numWaitingOn = 1
			else:
				print("Error: Consistency level isn't \'quorum\' or \'one\'")
				sys.exit(1)

		# If this replica is in quorum and consistency level is one, then immediately
		# respond to the client before contacting rest of the quorum
		if (numWaitingOn == 0):
			responseToClient = keyStore_pb2.ReplicaMessage()
			responseToClient.coordinator_response.value = value
			sock.sendall(responseToClient.SerializeToString())

		# Send writes to the other replicas in the quorum (but not to this one)
		for replicaID in quorum:
			if (not (replicaID in self.replicaPorts.keys())):
				continue
			if (replicaID != self.replicaName):
				putMessage = keyStore_pb2.ReplicaMessage()
				putMessage.src_replicaID = self.replicaName
				putMessage.dst_replicaID = replicaID
				putMessage.put_message.key = key
				putMessage.put_message.value = value
				putMessage.put_message.timestamp = str(ts)
				try:
					self.replicaPorts[replicaID].sendall( \
											putMessage.SerializeToString())
				except KeyError as e:
					print "KeyError: " + str(e)
					print("Key " + replicaID + " isn't in", self.replicaPorts)
					sys.exit(1)

		# Get responses from replicas in the quorum
		for replicaID in quorum:
			if (not (replicaID in self.replicaPorts.keys())):
				continue

			# Only wait for messages from replicas different than this one
			if (replicaID != self.replicaName):
				port = self.replicaPorts[replicaID]
				port.settimeout(2.0)
				try:
					msg = port.recv(1024)
					returnedMessage = keyStore_pb2.ReplicaMessage()
					returnedMessage.ParseFromString(msg)
					typeOfReturnedMessage = returnedMessage.WhichOneof(\
														  "replica_message")
					if (typeOfReturnedMessage != "return_put_message"):
						print("Error: Unsupported type of return message")
						sys.exit(1)

					# If numWaitingOn == 1 (and we're about to decrement to 0),
					# then we can return message to Client
					if (numWaitingOn == 1):
						responseToClient = keyStore_pb2.ReplicaMessage()
						responseToClient.coordinator_response.value = value
						sock.sendall(responseToClient.SerializeToString())

					numWaitingOn = numWaitingOn - 1

				except socket.timeout:
					print("Didn't receive a response message from replicaID: " +\
							replicaID)
				# Whether you received a response back or not, set the port back
				# to non-blocking (timeout == 0)
				finally:
					port.settimeout(0)
	
		# TODO : Probably need to implement Hinted Handoff stuff here (and in
		#        the above 'except' block)
		if (numWaitingOn > 0):
			print("Error: Did not receive enough responses from other replicas" \
					+ " in the quorum")
			# Send exception message back to Client
			responseToClient = keyStore_pb2.ReplicaMessage()
			responseToClient.coordinator_exception.errorMessage = "Key " + \
					str(key) + " cannot be put because the consistency level " +\
					"wasn't satisfied"
			sock.sendall(responseToClient.SerializeToString())


	def process_coordinatorResponseMessage(self, sock, message):
		print("Received coordinatorResponseMessage message")

	def process_coordinatorExceptionMessage(self, sock, message):
		print("Received coordinatorExceptionMessage message")
		returnMessage = keyStore_pb2.ReplicaMessage()

		# If the errorMessage is "Abort", then we just need to send back an ack
		# on the appropriate port in self.replicaPorts
		if (message.coordinator_exception.errorMessage == "Abort"):
			returnMessage.src_replicaID = self.replicaName
			returnMessage.dst_replicaID = message.src_replicaID
			returnMessage.coordinator_response.value = "Abort Return"
			if (not (message.src_replicaID in self.replicaPorts)):
				return -1
			returningPort = self.replicaPorts[str(message.src_replicaID)]
			returningPort.sendall(returnMessage.SerializeToString())
			returningPort.shutdown(socket.SHUT_RDWR)
			returningPort.close()
			self.replicaPorts.pop(message.src_replicaID)
			
			# Remove this thread from self.threads array
			self.threads.remove(threading.current_thread())	
			return -1
		return 0
	

	def process_getMessage(self, sock, message):
		print("Received getMessage message")
		key = message.get_message.key
		returnMessage = keyStore_pb2.ReplicaMessage()
		returnMessage.src_replicaID = self.replicaName
		returnMessage.dst_replicaID = message.src_replicaID

		# If key is in dataDictionary
		if (key in self.dataDictionary.keys()):
			value = self.dataDictionary[key][0]
			returnMessage.return_get_message.value = value
			returnMessage.return_get_message.notFound = False
			returnMessage.return_get_message.timestamp = \
						str(self.dataDictionary[key][1])

		# Else (key isn't in dataDictionary)
		else:
			returnMessage.return_get_message.value = ""
			returnMessage.return_get_message.notFound = True
			returnMessage.return_get_message.timestamp = str(datetime.min)
		
		# Send message to Coordinator	
		sock.sendall(returnMessage.SerializeToString())

	def process_putMessage(self, sock, message):
		print("Received putMessage message")
		
		key = message.put_message.key
		value = message.put_message.value
		ts = datetime.strptime(message.put_message.timestamp, '%Y-%m-%d %H:%M:%S.%f')
		response = "Updated"
		
		# If the key isn't yet stored in the dataDictionary, then it must have
		# a valid timestamp. So, update WAL and update dataDictionary
		if (not (key in self.dataDictionary.keys())):
			self.updateWAL(key, value,ts)
			self.dataDictionary[key] = [value, ts]
			
		# Else (key is stored in dataDictionary)
		else:
			storedTimestamp = self.dataDictionary[key][1]
			# If storedTimestamp < ts, then  update
			if (storedTimestamp < ts):
				self.updateWAL(key, value,ts)
				self.dataDictionary[key] = [value, ts]
			# There was no need to update b/c storedTimestamp > ts
			else:
				response = "No need to update"

		# Return message back to Coordinator
		returnMessage = keyStore_pb2.ReplicaMessage()
		returnMessage.src_replicaID = self.replicaName
		returnMessage.dst_replicaID = message.src_replicaID
		returnMessage.return_put_message.messageString = response
		sock.sendall(returnMessage.SerializeToString())

	def process_returnPutMessage(self, sock, message):
		print("Received returnPutMessage message")

	def process_returnGetMessage(self, sock, message):
		print("Received returnGetMessage message")
		# Receiving a get message from replica with value and timestamp 

	def process_replicaInitMessage(self, sock, receivedMessage):
		print("Received replicaInitMessage message")
		newReplicaID = receivedMessage.src_replicaID
		
		# Close socket from this replica to the new replica if there is one open
		if (newReplicaID in self.replicaPorts.keys()):
			print "\talready have a port for this new replica. So delete it and" \
					+ " open a new one"
			sock = self.replicaPorts[newReplicaID]
			print("Closing port from this replica to " + newReplicaID)
			sock.shutdown(socket.SHUT_RDWR)
			sock.close()
			self.replicaPorts.pop(newReplicaID)
		
		# Create a new socket from this replica to the new replica and store it
		newIpAddress = receivedMessage.replica_init_message.ipAddress
		newPortNumber = receivedMessage.replica_init_message.portNumber
		while True:
			try:
				sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
				sock.connect((newIpAddress, newPortNumber))
				self.replicaPorts[newReplicaID] = sock
				break
			except:
				continue
		
 		print("Connected to replica " + newReplicaID + " with IP address " +\
				 newIpAddress + " and port number " + str(newPortNumber))


	# Given a key (integer between 0, inclusive, and 255, inclusive), return an array
	# of strings of the replica names that store this key
	def getQuorum(self, key):
		if (key >= 0 and key <= 63):
			return [self.replicaNames[0], self.replicaNames[1], self.replicaNames[2]]
		elif (key >= 64 and key <= 127):
			return [self.replicaNames[1], self.replicaNames[2], self.replicaNames[3]]
		elif (key >= 128 and key <= 191):
			return [self.replicaNames[2], self.replicaNames[3], self.replicaNames[0]]
		elif (key >= 192 and key <= 255):
			return [self.replicaNames[3], self.replicaNames[0], self.replicaNames[1]]
		else:
			print("Error: Key should be between 0 (inclusive) and 255 (inclusive)." \
					+ " Key = " + str(key))
			sys.exit(1)

	# Helper function used by process_getRequestClient function to determine what the
	# latest value is from all replicas in the quorum
	def getLatestValue(self, array):
		maxTime = datetime.min
		returnValue = ""
		for element in array:
			if (element[1] > maxTime):
				maxTime = element[1]
				returnValue = element[0]
		if (maxTime == datetime.min):
			return -1
		else:
			return returnValue

	def getLatestTimestamp(self, array):
		maxTime = datetime.min
		for element in array:
			if (element[1] > maxTime):
				maxTime = element[1]

		return maxTime

	# Function that takes in a key and value, and updates
        # the fileName with the key and value you're putting
	def updateWAL(self, key, value, timestamp):
	        f = open(self.WALFileName, "a+")
                f.write(str(key) + " " + str(value) + " " + str(timestamp) + "\n")
                f.close()

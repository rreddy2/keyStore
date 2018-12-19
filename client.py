#!/usr/bin/env python

import sys
import socket
import keyStore_pb2
import signal

sys.path.append('/home/vchaska1/protobuf/protobuf-3.5.1/python')
	
# Invalid format print statement
formatString = "Input must be one of the two following forms:\n" + 	\
				"get <key> <one/quorum>\n" + 						\
				"put <key> <value> <one/quorum>"
def isInteger(str):
	try:
		int(str)
		return True
	except ValueError:
		return False


def main():
	numberOfArgs = len(sys.argv)

	if (numberOfArgs != 3):
		print("Usage: ./client <coordinator-IP> <coordinator-port>")
		sys.exit(1)

	coordinatorIP = sys.argv[1]

	if (not isInteger(sys.argv[2])):
		print("<coordinator-port> must be an integer")
		sys.exit(1)

	coordinatorPort = int(sys.argv[2])

	# Open up connection with the coordinator
	sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	sock.connect((coordinatorIP, coordinatorPort))

	try:
		while True:
			# Receive input from user
			userInput = raw_input("...>")

			# Need to parse the user input and populate a Get/Put Request Message
			# Object and send object over the TCP socket
			# Input must be one of the two following forms:
			# get <key> <one/quorum>
			# put <key> <value> <one/quorum>
			words = userInput.split()
			if (len(words) < 3 or len(words) > 4):
				print("Error: Invalid input")
				print(formatString)
				continue
			if (words[0] == "get"):

				# Must be 3 words in a get command. Also, key must be an integer
				if (len(words) != 3 or not isInteger(words[1])):
					print("Error: Invalid input")
					print(formatString)
					continue

				key = int(words[1])
				consistencyLevel = words[2]

				if (not keyIsInRange(key)):
					continue	

				if (not consistencyLevelIsOk(consistencyLevel)):
					continue

				# Create a keyStore message object
				message = keyStore_pb2.ReplicaMessage()
				message.get_request.key = key
				message.get_request.consistencyLevel = consistencyLevel

				# Send the message over the socket to coordinator
				sock.sendall(message.SerializeToString())

				# Get response from Coordinator
				msg = sock.recv(1024)
				returnedMessage = keyStore_pb2.ReplicaMessage()
				returnedMessage.ParseFromString(msg)
				typeOfReturnedMessage = returnedMessage.WhichOneof("replica_message")
				if (typeOfReturnedMessage == "coordinator_response"):
					print("\tKey: " + str(key) +  ", Value:" + \
							returnedMessage.coordinator_response.value)

				elif (typeOfReturnedMessage == "coordinator_exception"):
					print("Client receieved Exception from the Coordinator: " + \
							returnedMessage.coordinator_exception.errorMessage)

				else:
					print("Client receieved a message of unsupported type: " + \
							str(typeOfReturnedMessage))

			elif (words[0] == "put"):

				# Must be 4 words in a put command. Also, key must be an integer
				if (len(words) != 4 or not isInteger(words[1])):
					print("Error: Invalid input")
					print(formatString)
					continue

				key = int(words[1])
				value = words[2]
				consistencyLevel = words[3]

				if (not keyIsInRange(key)):
					continue	

				if (not consistencyLevelIsOk(consistencyLevel)):
					continue

				# Create a keyStore message object
				message = keyStore_pb2.ReplicaMessage()
				message.put_request.key = key
				message.put_request.value = value
				message.put_request.consistencyLevel = consistencyLevel

				# Send the message over the socket to coordinator
				sock.sendall(message.SerializeToString())

				# Get response from Coordinator
				msg = sock.recv(1024)
				returnedMessage = keyStore_pb2.ReplicaMessage()
				returnedMessage.ParseFromString(msg)
				typeOfReturnedMessage = returnedMessage.WhichOneof("replica_message")
				if (typeOfReturnedMessage == "coordinator_response"):
					#print("\tKey: " + str(key) +  ", Value:" + \
					#		returnedMessage.coordinator_response.value)
					pass

				elif (typeOfReturnedMessage == "coordinator_exception"):
					print("Client receieved Exception from the Coordinator: " + \
							returnedMessage.coordinator_exception.errorMessage)

				else:
					print("Client receieved a message of unsupported type: " + \
							typeOfReturnedMessage)
			else:
				print("Incorrect String Formatting")
				print(formatString)

	except KeyboardInterrupt:
		print "Receiving KeyboardInterrupt"
		print "Exiting Program..."
		sock.close()
		exit(1)

# Consistency Level must be either "one" or "quorum"
def consistencyLevelIsOk(consistencyLevel):
	if (consistencyLevel == "one" or consistencyLevel == "quorum"):
		return True
	else:
		print("Error: Consistency level must be \"one\" or \"quorum\"")
		print(formatString)
		return False

			
# Key must be between 0 (inclusive) and 255 (inclusive)
def keyIsInRange(key):
	if (key >= 0 and key <= 255):
		return True
	else:
		print("Error: Key must be in between 0 (inclusive) and 255 (inclusive)")
		print(formatString)
		return False

main()

from constants import clientPackets
from common.log import logUtils as log
from helpers import chatHelper as chat
import time

def handle(userToken, packetData):
	# Send private message packet
	packetData = clientPackets.sendPrivateMessage(packetData)
	chat.sendMessage(token=userToken, to=packetData["to"], message=packetData["message"])
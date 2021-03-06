import sys
import time
import traceback

from datetime import datetime

from common.constants import privileges
from common.log import logUtils as log
from common.ripple import userUtils
from constants import exceptions
from constants import serverPackets
from helpers import chatHelper as chat
from helpers import countryHelper
from helpers import locationHelper
from objects import glob


def handle(tornadoRequest):
	# Data to return
	responseToken = None
	responseTokenString = "ayy"
	responseData = bytes()

	# Get IP from tornado request
	requestIP = tornadoRequest.getRequestIP()

	# Avoid exceptions
	clientData = ["unknown", "unknown", "unknown", "unknown", "unknown"]
	osuVersion = "unknown"

	# Split POST body so we can get username/password/hardware data
	# 2:-3 thing is because requestData has some escape stuff that we don't need
	loginData = str(tornadoRequest.request.body)[2:-3].split("\\n")
	try:
		# Make sure loginData is valid
		if len(loginData) < 3:
			raise exceptions.invalidArgumentsException()

		# Get HWID, MAC address and more
		# Structure (new line = "|", already split)
		# [0] osu! version
		# [1] plain mac addressed, separated by "."
		# [2] mac addresses hash set
		# [3] unique ID
		# [4] disk ID
		splitData = loginData[2].split("|")
		osuVersion = splitData[0]
		timeOffset = int(splitData[1])
		clientData = splitData[3].split(":")[:5]
		if len(clientData) < 4:
			raise exceptions.forceUpdateException()

		# Try to get the ID from username
		username = str(loginData[0])
		userID = userUtils.getID(username)

		if not userID:
			# Invalid username
			raise exceptions.loginFailedException()
		if not userUtils.checkLogin(userID, loginData[1]):
			# Invalid password
			raise exceptions.loginFailedException()

		# Make sure we are not banned or locked
		priv = userUtils.getPrivileges(userID)
		if userUtils.isBanned(userID) and priv & privileges.USER_PENDING_VERIFICATION == 0:
			raise exceptions.loginBannedException()
		if userUtils.isLocked(userID) and priv & privileges.USER_PENDING_VERIFICATION == 0:
			raise exceptions.loginLockedException()

		# 2FA check
		if userUtils.check2FA(userID, requestIP):
			log.warning("Need 2FA check for user {}.".format(loginData[0]))
			raise exceptions.need2FAException()

		# No login errors!

		# Verify this user (if pending activation)
		firstLogin = False
		if priv & privileges.USER_PENDING_VERIFICATION > 0 or not userUtils.hasVerifiedHardware(userID):
			if userUtils.verifyUser(userID, clientData):
				# Valid account
				log.info("Account {} verified successfully!".format(userID))
				glob.verifiedCache[str(userID)] = 1
				firstLogin = True
			else:
				# Multiaccount detected
				log.info("Account {} NOT verified!".format(userID))
				glob.verifiedCache[str(userID)] = 0
				raise exceptions.loginBannedException()


		# Save HWID in db for multiaccount detection
		hwAllowed = userUtils.logHardware(userID, clientData, firstLogin)

		# This is false only if HWID is empty
		# if HWID is banned, we get restricted so there's no
		# need to deny bancho access
		if not hwAllowed:
			raise exceptions.haxException()

		# Log user IP
		userUtils.logIP(userID, requestIP)

		# Delete old tokens for that user and generate a new one
		isTournament = "tourney" in osuVersion
		if not isTournament:
			glob.tokens.deleteOldTokens(userID)
		responseToken = glob.tokens.addToken(userID, requestIP, timeOffset=timeOffset, tournament=isTournament)
		responseTokenString = responseToken.token

		# Check restricted mode (and eventually send message)
		responseToken.checkRestricted()

		userFlags = userUtils.getUserFlags(userID)
		if userFlags > 0: # Pending public bans. Such as chargebacks, etc.
			flagReason = userUtils.getFlagReason(userID)
			if userFlags-int(time.time()) < 0:
				responseToken.enqueue(serverPackets.notification("Your account has been automatically restricted due to a pending restriction not being having been dealt with.\n\nReason: {}".format(flagReason)))
				userUtils.restrict(userID)
				userUtils.setUserFlags(userID, 0)
				log.cmyui("{} has been automatically restricted due to not dealing with pending restriction. Reason: {}.".format(username, flagReason), discord="cm")
				log.rap(userID, "has been restricted due to a pending restriction. Reason: {}.".format(flagReason))
			else:
				if "charge" in flagReason:
					responseToken.enqueue(serverPackets.notification("Your account has been flagged with an automatic restriction.\n\nIt will occur at {time} if not dealt with.\n"
						"Reason: {reason}\n\nTo avoid being restricted for this behaviour, you can cancel or revert your chargeback before your restriction date.".format(time=datetime.utcfromtimestamp(int(userFlags)).strftime('%Y-%m-%d %H:%M:%S'), reason=flagReason)))
				elif "live" in flagReason:
					responseToken.enqueue(serverPackets.notification("Your account has been flagged with an automatic restriction.\n\nIt will occur at {time} if not dealt with.\n"
						"Reason: {reason}\n\nThis means you are required to submit a liveplay to avoid this. This only happens in cases when we are confident in foul play; and are offering you this opportunity as a final stance to prove your legitimacy, against all the odds.".format(time=datetime.utcfromtimestamp(int(userFlags)).strftime('%Y-%m-%d %H:%M:%S'), reason=flagReason)))
				else:
					responseToken.enqueue(serverPackets.notification("Your account has been flagged with an automatic restriction.\n\nIt will occur at {time} if not dealt with.\n"
						"Reason: {reason}\n\nYou have until the restriction to deal with the issue.".format(time=datetime.utcfromtimestamp(int(userFlags)).strftime('%Y-%m-%d %H:%M:%S'), reason=flagReason)))

		# Send message if premium / donor expires soon
		# ok spaghetti code time
		if responseToken.privileges & privileges.USER_DONOR:
			donorType = 'premium' if responseToken.privileges & privileges.USER_PREMIUM else 'donor'

			expireDate = userUtils.getDonorExpire(responseToken.userID)
			if expireDate-int(time.time()) < 0:
				userUtils.setPrivileges(userID, 3)
				log.cmyui("{}'s donation perks have been removed as their time has run out.".format(username), discord="cm")
				log.rap(userID, "User's donor perks have been removed as their time has run out.")
				responseToken.enqueue(serverPackets.notification("Your {donorType} tag has expired! Thank you so much for the support, it really means everything to us. If you wish to keep supporting Akatsuki and you don't want to lose your {donorType} privileges, you can donate again by clicking on 'Support us' on Akatsuki's website.".format(donorType=donorType)))
			elif expireDate-int(time.time()) <= 86400*3:
				expireDays = round((expireDate-int(time.time()))/86400)
				expireIn = "{} days".format(expireDays) if expireDays > 1 else "less than 24 hours"
				responseToken.enqueue(serverPackets.notification("Your {donorType} tag expires in {expireIn}! When your {donorType} tag expires, you won't have any of the {donorType} privileges, like yellow username, custom badge and discord custom role and username color! If you wish to keep supporting Akatsuki and you don't want to lose your {donorType} privileges, you can donate again by clicking on 'Support us' on Akatsuki's website.".format(donorType=donorType, expireIn=expireIn)))

		""" Akatsuki does not use 2fa! we suck!
		if userUtils.deprecateTelegram2Fa(userID):
			responseToken.enqueue(serverPackets.notification("As stated on our blog, Telegram 2FA has been deprecated on 29th June 2018. Telegram 2FA has just been disabled from your account. If you want to keep your account secure with 2FA, please enable TOTP-based 2FA from our website https://akatsuki.pw. Thank you for your patience."))
		"""
		
		# Set silence end UNIX time in token
		responseToken.silenceEndTime = userUtils.getSilenceEnd(userID)

		# Get only silence remaining seconds
		silenceSeconds = responseToken.getSilenceSecondsLeft()

		# Get supporter/GMT
		userGMT = False
		userSupporter = True
		userTournament = False
		if responseToken.admin:
			userGMT = True
		if responseToken.privileges & privileges.USER_TOURNAMENT_STAFF > 0:
			userTournament = True

		# Server restarting check
		if glob.restarting:
			raise exceptions.banchoRestartingException()

		# Send login notification before maintenance message
		if glob.banchoConf.config["loginNotification"] != "":
			responseToken.enqueue(serverPackets.notification(glob.banchoConf.config["loginNotification"]))

		# Maintenance check
		if glob.banchoConf.config["banchoMaintenance"]:
			if not userGMT:
				# We are not mod/admin, delete token, send notification and logout
				glob.tokens.deleteToken(responseTokenString)
				raise exceptions.banchoMaintenanceException()
			else:
				# We are mod/admin, send warning notification and continue
				responseToken.enqueue(serverPackets.notification("Akatsuki is currently in maintenance mode. Only admins have full access to the server.\nType '!system maintenance off' in chat to turn off maintenance mode."))

		# Send all needed login packets
		responseToken.enqueue(serverPackets.silenceEndTime(silenceSeconds))
		responseToken.enqueue(serverPackets.userID(userID))
		responseToken.enqueue(serverPackets.protocolVersion())
		responseToken.enqueue(serverPackets.userSupporterGMT(userSupporter, userGMT, userTournament))
		responseToken.enqueue(serverPackets.userPanel(userID, True))
		responseToken.enqueue(serverPackets.userStats(userID, True))

		# Channel info end (before starting!?! wtf bancho?)
		responseToken.enqueue(serverPackets.channelInfoEnd())
		# Default opened channels
		# TODO: Configurable default channels
		chat.joinChannel(token=responseToken, channel="#osu")
		chat.joinChannel(token=responseToken, channel="#announce")

		#Akatsuki extra channels
		chat.joinChannel(token=responseToken, channel="#nowranked")
		chat.joinChannel(token=responseToken, channel="#request")

		# Join admin channel if we are an admin
		if responseToken.admin or responseToken.privileges & privileges.USER_PREMIUM:
			chat.joinChannel(token=responseToken, channel="#admin")

		# Output channels info
		for key, value in glob.channels.channels.items():
			if value.publicRead and not value.hidden:
				responseToken.enqueue(serverPackets.channelInfo(key))

		# Send friends list
		responseToken.enqueue(serverPackets.friendList(userID))

		# Send main menu icon
		if glob.banchoConf.config["menuIcon"] != "":
			responseToken.enqueue(serverPackets.mainMenuIcon(glob.banchoConf.config["menuIcon"]))

		# Send online users' panels
		with glob.tokens:
			for _, token in glob.tokens.tokens.items():
				if not token.restricted:
					responseToken.enqueue(serverPackets.userPanel(token.userID))

		# Get location and country from ip.zxq.co or database. If the user is a donor, then yee
		if glob.localize and (firstLogin == True or responseToken.privileges & privileges.USER_DONOR <= 0):
			# Get location and country from IP
			latitude, longitude = locationHelper.getLocation(requestIP)
			countryLetters = locationHelper.getCountry(requestIP)
			country = countryHelper.getCountryID(countryLetters)
		else:
			# Set location to 0,0 and get country from db
			log.warning("Location skipped")
			latitude = 0
			longitude = 0
			countryLetters = "XX"
			country = countryHelper.getCountryID(userUtils.getCountry(userID))

		# Set location and country
		responseToken.setLocation(latitude, longitude)
		responseToken.country = country

		# Set country in db if user has no country (first bancho login)
		if userUtils.getCountry(userID) == "XX":
			userUtils.setCountry(userID, countryLetters)

		# Send to everyone our userpanel if we are not restricted or tournament
		if not responseToken.restricted:
			glob.streams.broadcast("main", serverPackets.userPanel(userID))

		# Set reponse data to right value and reset our queue
		responseData = responseToken.queue
		responseToken.resetQueue()
	except exceptions.loginFailedException:
		# Login failed error packet
		# (we don't use enqueue because we don't have a token since login has failed)
		responseData += serverPackets.loginFailed()
	except exceptions.invalidArgumentsException:
		# Invalid POST data
		# (we don't use enqueue because we don't have a token since login has failed)
		responseData += serverPackets.loginFailed()
		responseData += serverPackets.notification("We see what you're doing..")
		log.cmyui("User {} has triggered invalidArgumentsException in loginEvent.py".format(userID), discord="cm")
	except exceptions.loginBannedException:
		# Login banned error packet
		responseData += serverPackets.loginBanned()
	except exceptions.loginLockedException:
		# Login banned error packet
		responseData += serverPackets.loginLocked()
	except exceptions.banchoMaintenanceException:
		# Bancho is in maintenance mode
		responseData = bytes()
		if responseToken is not None:
			responseData = responseToken.queue
		responseData += serverPackets.notification("Akatsuki is currently in maintenance mode. Please try to login again later.")
		responseData += serverPackets.loginFailed()
	except exceptions.banchoRestartingException:
		# Bancho is restarting
		responseData += serverPackets.notification("Akatsuki is restarting. Try again in a few minutes.")
		responseData += serverPackets.loginFailed()
	except exceptions.need2FAException:
		# User tried to log in from unknown IP
		responseData += serverPackets.needVerification()
	except exceptions.haxException:
		# Using oldoldold client, we don't have client data. Force update.
		# (we don't use enqueue because we don't have a token since login has failed)
		responseData += serverPackets.forceUpdate()
		responseData += serverPackets.notification("Custom clients of ANY kind are NOT PERMITTED on Akatsuki. Please login using the current osu! client.")
		log.cmyui("User {} has logged in with a VERY old client".format(userID), discord="cm")
	except:
		log.error("Unknown error!\n```\n{}\n{}```".format(sys.exc_info(), traceback.format_exc()))
	finally:
		# Console and discord log
		if len(loginData) < 3:
			log.info("Invalid bancho login request from **{}** (insufficient POST data)".format(requestIP), "bunker")

		# Return token string and data
		return responseTokenString, responseData

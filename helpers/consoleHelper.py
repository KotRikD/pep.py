from common.constants import bcolors
from objects import glob

def printServerStartHeader(asciiArt=True):
	"""
	Print server start message

	:param asciiArt: print BanchoBoat ascii art. Default: True
	:return:
	"""
	if asciiArt:
		print("{}      _/_/    _/                    _/                          _/        _/   ".format(bcolors.GREEN))
		print("   _/    _/  _/  _/      _/_/_/  _/_/_/_/    _/_/_/  _/    _/  _/  _/          ")
		print("  _/_/_/_/  _/_/      _/    _/    _/      _/_/      _/    _/  _/_/      _/     ")
		print(" _/    _/  _/  _/    _/    _/    _/          _/_/  _/    _/  _/  _/    _/      ")
		print("_/    _/  _/    _/    _/_/_/      _/_/  _/_/_/      _/_/_/  _/    _/  _/       \r\n")
		print("")
		print("                          .. o  .")
		print("                         o.o o . o")
		print("                        oo...")
		print("                    __[]__")
		print("   cmyui -->  _\\:D/_/o_o_o_|__     u wot m8")
		print("             \\\"\"\"\"\"\"\"\"\"\"\"\"\"\"/")
		print("              \\ . ..  .. . /")
		print("^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^{}".format(bcolors.ENDC))

	printColored("> Welcome to pep.py osu!bancho server v{}".format(glob.VERSION), bcolors.GREEN)
	printColored("> Made by the Ripple and Akatsuki teams", bcolors.GREEN)
	printColored("> {}https://github.com/osuAkatsuki/pep.py".format(bcolors.UNDERLINE), bcolors.GREEN)
	printColored("> Press CTRL+C to exit\n", bcolors.GREEN)

def printNoNl(string):
	"""
	Print a string without \n at the end

	:param string: string to print
	:return:
	"""
	print(string, end="")

def printColored(string, color):
	"""
	Print a colored string

	:param string: string to print
	:param color: ANSI color code
	:return:
	"""
	print("{}{}{}".format(color, string, bcolors.ENDC))

def printError():
	"""
	Print a red "Error"

	:return:
	"""
	printColored("Error", bcolors.RED)

def printDone():
	"""
	Print a green "Done"

	:return:
	"""
	printColored("Done", bcolors.GREEN)

def printWarning():
	"""
	Print a yellow "Warning"

	:return:
	"""
	printColored("Warning", bcolors.YELLOW)

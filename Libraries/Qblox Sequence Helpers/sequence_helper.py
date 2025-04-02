"""
seqeuence_helper.py		v 1.0

This is a library of useful functions to make Qblox sequencing faster and more user-friendly.
See sequence_helper_tutorial.ipynb to learn how to use this library.

Created: 		Nov 28, 2024
Last updated: 	Dec 16, 2024
Tested:			Dec 16, 2024
				On firmware:			0.9.2
				On qblox-instruments:	0.14.2	

Author: Kyle MacRobbie
"""

# Imports
import scipy
import math
import matplotlib.pyplot as plt
from qblox_instruments.qcodes_drivers.module import Module
import numpy as np
import inspect

def make_waveforms(specs:dict):
	"""Function that takes a dictionary of values with the parameters
	of a waveform, and returns a dictionary with the requested data
	
	specs will have the form:
	{
	'name': [type, length, magnitude, index],
	}

	or for a ramp:
	{
	'name': [type, length, initial voltage, final voltage, index],
	}
	
	Supported types are:
		- 'block'
		- 'gaussian'
		- 'sine'
		- 'cosine'
		- 'ramp'
	"""

	output = {}   # Creating a dictionary to store the waveforms in

	# Loop through each instruction and create the corresponding waveform, then add that waveform to the output dictionary
	for name in specs:
		data = []

		if specs[name][0] == 'block':
			data = [specs[name][2] for i in range(0, specs[name][1])]

		elif specs[name][0] == 'gaussian':
			data = scipy.signal.windows.gaussian(specs[name][1], std=0.12 * specs[name][1]).tolist()

		elif specs[name][0] == 'sine':
			data = [math.sin((2 * math.pi / specs[name][1]) * i) for i in range(0, specs[name][1])]

		elif specs[name][0] == 'cosine':
			data = [math.cos((2 * math.pi / specs[name][1]) * i) for i in range(0, specs[name][1])]

		elif specs[name][0] == 'ramp':
			data = [(((specs[name][3] - specs[name][2]) / (specs[name][1])) * i) + specs[name][2] for i in range(0, specs[name][1])]

		else:
			print(f"ERROR: waveform type '{specs[name][0]}' is not supported by make_waveforms().\nSee the docstring at the start of the function for supported waveforms")
			data = None


		output[name] = {} # Add a new entry to the waveform dictionary
		output[name]['data'] = data	# Add the data to this new entry
		output[name]['index'] = int(specs[name][len(specs[name]) - 1]) # Add the index to this new entry

	return output

def plot_waveforms(waveforms):
	"""Function that takes a waveform dictionary
	and plots the waveforms"""

	# Generate the plot
	fig, ax = plt.subplots(1, 1, figsize = (14, 4))

	# Loop through each waveform given and plot it with the given label
	for wave in waveforms:
		ax.plot(waveforms[wave]['data'], label = wave)

	# Set titles
	ax.set_title("Waveforms")
	ax.set_xlabel("Time [ns]")
	ax.set_ylabel("Amplitude [a.u.]")
	
	# Add a grid to the plot
	ax.grid(ls = '--')

	# Display a legend
	plt.legend()

	plt.show()
	return None

def make_output_sequence(input:list, module:str, iterations:int = 1, plot = False):
	"""Function that generates a Q1ASM sequence for a series of gate 
	voltages and ramps based on the input.
	
	The function also specifies whether the gates are being controlled
	by the QRM or QCM. The 'module' arguement can either be
		- 'qrm'
		- 'qcm'
	
	The input is a list where each entry is either a square
	pulse or a ramp.
	
	The input list will take the form:

		For square pulses
		[
			['type', 'length', 'magnitude']
		]
	
		For ramps
		[
			['type', 'length', 'start value', 'end value']
		]

		Supported types:
			- 'square'
			- 'ramp'
	
	The input list should be in the order in which the voltages should be executed.
	"""

	# This will extract the line of code in the python notebook that called this function
	# By the naming convention of the modules, the first three letters of that line will be either "qrm" or "qcm" from the name of the module.
	interpreted_module = str(inspect.getframeinfo(inspect.currentframe().f_back)[3][0])
	i = 0
	for char in interpreted_module:
		if char != '	':
			break
		else:
			i += 1
	
	# i will be the index of the first non-tab character. This will take any indentatoin into account
	interpreted_module = interpreted_module[i:i+3]

	# Check to see if the first three letters of that line are indeed the names of one of the modules. 
	# If not, it is most likely that the naming convention has not been followed.
	if interpreted_module != 'qcm' and interpreted_module != 'qrm':
		print(f"ERROR: module name not recognized ({interpreted_module}). Please name your modules one of the following:\n\t- qrm_module\n\t- qcm_module\n\nIf you are trying to sequence an RF module, please use make_rf_sequence() instead of make_output_sequence().")
		return None

	module_range = 0		# Just setting up this variable
	awg_offs_range = 32767	# The range of values that can be passed into the Q1ASM command set_awg_offs

	# Determine what module is being used, make sure the module given to the function and the previously extracted module name correspond to the same module
	# This is a precaution since if you accidentally pass "qrm" to the function while using the QCM, you will get 5x the voltage in the output
	# Since the QCM has 5x the range as the QRM. So this double-checking prevents that from happening.
	if module == "qcm" and interpreted_module == "qcm":
		module_range = 2.5
	elif module == "qrm" and interpreted_module == "qrm":
		module_range = 0.5
	elif module == "qrm" and interpreted_module == "qcm":
		print("ERROR: module name and module passed into make_output_sequence() do not match.")
		return None
	elif module == "qcm" and interpreted_module == "qrm":
		print("ERROR: module name and module passed into make_output_sequence() do not match.")
		return None
	else:
		print("ERROR: module type not supported by make_sequence()\nSee the docstring at the start of the function for supported module types.")
		return None

	# Find the total length of all ramps, to see if waveforms can be used.
	ramp_len = 0
	for step in input:
		if step[0] == 'ramp':
			ramp_len += step[1]

	# If the total length of all the ramps is less than the maximum length of waveforms that can be passed to a sequencer (16384 ns),
	# Then we will use waveforms to make the ramps as these will have the best resolution of any ramping method.
	if ramp_len <= 16384:
		# Since we can't have a waveform with a magnitude greater than 1, if a ramp spans more than half of the output range, 
		# the funciton will raise an error.
		# To rememdy this, any ramp crossing 0 V will be split into two ramps, one going from start to 0 and the other going from 0 to end.
		input_range_corrected = [] # Where the new input list will be stored
		# Looping through each step to see if it needs to be broken up into two separate steps
		for step in input:
			if step[0] == 'ramp' and ((step[2] > 0 and step[3] < 0) or ((step[2] < 0 and step[3] > 0))):
				# If it is a ramp that crosses 0
				# Find the time that it crosses 0, and split into two waveforms and steps
				ramp_lenght = step[1]
				per = abs(step[2]) / (abs(step[2]) + abs(step[3])) # decimal percentage of the amount of ramp time that has to be spent on the first ramp
				first_length = round(ramp_lenght)*per # Length of the first ramp
				second_length = ramp_lenght - first_length # Length of the second ramp, calculated from the first ramp

				# Make sure neither length is less than 4, and if it is then set it to 4
				if first_length < 4:
					first_length = 4
					second_length = ramp_lenght - first_length
				if second_length < 4:
					second_length = 4
					first_length = ramp_lenght - second_length

				first_ramp = ['ramp', first_length, step[2], 0]	# New step for the first ramp
				second_ramp = ['ramp', second_length, 0, step[3]] # New step for the second ramp
				input_range_corrected.append(first_ramp)	# Add our new ramps to the list
				input_range_corrected.append(second_ramp)
			else:
				# If it does not cross zero, keep the step as it is
				input_range_corrected.append(step)
		input = input_range_corrected

		# Initializing our sequence string variable
		sequence = f""""""

		# Check to see if we need to add looping
		if iterations > 1:
			sequence += f"""	move	{int(iterations)},R0\n	loop:"""

		# Setting up the waveforms dictionary and the sequence string.
		waveform_specs = {}
		sequence += """\n	wait_sync	4"""

		# Looping through the input list, adding to the sequence string and waveforms dictionary as needed.
		waveform_index = 0
		temp_str = """"""

		for step in input:
			# Check what type of step it is (square or ramp).
			step_type = step[0]
			step_len = int(step[1])

			if step_type == "square":
				
				offset = step[2]
				offset_q1 = round((offset/module_range)*awg_offs_range) # Convert the offset to the Q1ASM value
				temp_str = f"""\n	set_awg_offs	{offset_q1},{offset_q1}\n	upd_param	{step_len}""" # Add the step to our sequence string
			
			elif step_type == "ramp":
				# For a ramp, the offset will first be set to whatever the final voltage of the ramp is
				# then the ramp will be played on top of that offset voltage, going from the difference between the start and end voltage to zero.
				start = (step[2] - step[3]) / module_range
				end = 0
				waveform_specs[str(waveform_index)] = ['ramp', step_len, start, end, waveform_index] # Waveform to be played on top of the offset
				new_offset = step[3] # Offset, also the final voltage and will be ramped to.
				new_offset_q1 = round((new_offset/module_range)*awg_offs_range) # Convert the offset to the Q1ASM value
				temp_str = f"""\n	set_awg_offs	{new_offset_q1},{new_offset_q1}\n	play	{waveform_index},{waveform_index},{step_len}""" # Add the step to our sequence string
				waveform_index += 1

			else:
				print("ERROR: step type not supported by make_sequence().\nSupported step types are 'square' and 'ramp'.")

			sequence += temp_str

		# Check to see if we need to add looping
		if iterations > 1:
			sequence += f"""\n	loop	R0,@loop"""

		# End by resetting the offset to 0 and stopping the sequence
		sequence += """\n	set_awg_offs	0,0\n	upd_param	4\n	stop"""

		# Generate the ramp waveforms and plot if plotting has been selected
		waveforms = make_waveforms(waveform_specs)
		if plot == True:
			plot_waveforms(waveforms)

	# If the amount of ramping is greater than 16384 ns, we cannot store all of the ramping in waveforms.
	# So we will have to create ramps by stepping the voltage with some resolution, that will be determined by how many steps we need
	# and how many commands we are allowed to pass into a sequence.
	else:
		# Before defining a resolution, we need to find the square steps to see how many commands we can use to make our ramps.
		# Since upd_param has a maximum wait time of 65535, if the square pulse is longer than that, we need to use multiple upd_param values.
		num_squares = 0
		for step in input:
			if step[0] == 'square':	# if this is a square pulse
				num_commands = math.ceil(step[1]/65535) # The number of steps that will be necessary to make this square pulse
				num_squares += num_commands

		num_subpulses = (12288 / 2) - 10 - (2*num_squares)	# Making sure we don't pass the 12288 instruction limit for the sequencer
		resolution = math.ceil(ramp_len / num_subpulses)	# Define the resolution based on how many instructions we can give
		if resolution < 8:	# There is a minimum resolution based on the time it takes to set a voltage using Q1ASM
			resolution = 8

		# Initializing out sequence string
		sequence_play = """"""

		# Loop through each step and add its commands to the sequence string
		for step in input:
			if step[0] == 'ramp':
				start_voltage = step[2]
				end_voltage = step[3]
				start_offset_q1 = round((start_voltage / module_range) * awg_offs_range) # Convert the offset to the Q1ASM value
				end_offset_q1 = round((end_voltage / module_range) * awg_offs_range) # Convert the offset to the Q1ASM value
				# Determine the voltage jump at each step. This is determined by dividing the entire range of the ramp by the 
				# number of steps it will ultimately use. Then it is converted to a Q1ASM value by adjusting for the module output
				# range multiplying by the Q1ASM command range
				num_steps = round(step[1]/resolution)
				step_size_q1 = (((end_voltage - start_voltage) / num_steps) / module_range) * awg_offs_range
				# Create a list of steps
				offsets_q1 = np.round(np.linspace(start_offset_q1, end_offset_q1 + step_size_q1, num_steps))
				# Loop through the steps, and add that steps commands to the sequence string
				for offset in offsets_q1:
					sequence_play += f"""\n	set_awg_offs	{int(offset)},{int(offset)}\n	upd_param	{int(resolution)}"""

			# If it is a square pulse
			elif step[0] == 'square':
				voltage = step[2]
				offset_q1 = round((voltage / module_range) * awg_offs_range) # Convert the offset to the Q1ASM value
				# If the square pulse is longer than 65535 ns, we need mutliple wait commands
				num_waits = math.floor(step[1]/65535) # How many full wait upd_param commands will have to be used
				remainder_wait = int(step[1]%65535)	# Leftover waiting that needs to be done
				# Add the correct amount of waiting
				for i in range(num_waits):
					sequence_play += f"""\n	set_awg_offs	{int(offset_q1)},{int(offset_q1)}\n	upd_param	65535"""
				if remainder_wait != 0:
					sequence_play += f"""\n	set_awg_offs	{int(offset_q1)},{int(offset_q1)}\n	upd_param	{remainder_wait}"""

		# Create the whole sequence be beginning with syncing, and ending with resetting the offset to 0 and stopping
		sequence = """\n	wait_sync	4""" + sequence_play + f"""\n	set_awg_offs	0,0\n	upd_param	4\n	stop"""
		waveforms = {}
		print(f"resolution for {module} output: {resolution} ns")

	# Create the sequence dictionary to be passed to the sequencer.
	sequence_dict = {
		"waveforms": waveforms,
		"weights": {},
		"acquisitions": {},
		"program": sequence
	}

	return sequence_dict

def make_rf_sequence(input:list, marker = None, iterations = 1):
	"""Function that generates a Q1ASM for rf pulses.
	
	The input list will take the form:

		For wait commands
		[
			['type', 'length']
		]
	
		For square pulses
		[
			['type', 'length', 'magnitude']
		]

		Supported types:
			- 'square'
			- 'wait'
	
	The input list should be in the order in which the voltages should be executed.
	"""

	# Initialize our sequence string
	seq = f""""""

	# Check if we need to loop:
	if iterations > 1:
		seq += f"""	move	{iterations},R0\n	loop:"""

	# Sync with other sequencers
	seq += f"""\n	wait_sync	4"""

	# Loop through the steps and add their commands to the sequence string
	for step in input:
		# Wait commands
		if step[0] == 'wait':
			seq += f"""\n	set_awg_offs	0,0"""	# Set the voltage to 0
			# Since the maximum wait time for an upd_param command is 65535 ns, we will need multiple commands if there are longer waits than 65535 ns.
			num_full_waits = math.floor(step[1]/65535)	# Number of full wait commands
			remainder = step[1]%65535	# Remaining wait time
			# Adding the wait time to the sequence string
			for i in range(num_full_waits):
				seq += f"""\n	upd_param	65535"""
			if remainder != 0:
				seq += f"""\n	upd_param	{remainder}"""

		# Square pulses
		elif step[0] == 'square':
			# Set the marker to the appropriate value
			if marker == 0:
				seq += f"""\n	set_mrk	{0b1001}"""
			elif marker == 1:
				seq += f"""\n	set_mrk	{0b0110}"""
			elif marker == 'both':
				seq += f"""\n	set_mrk {0b1111}"""
			elif marker == None:
				None
			else:
				print("ERROR: marker type not supported. Supported arguements are:\n- 0\n- 1\n- 'both'")
			
			awg_offs_range = 32767	# The range of values that can be passed into the Q1ASM command set_awg_offs
			offset = step[2]	# Voltage to set the offset to
			offset_q1 = round((offset)*awg_offs_range) # Convert the offset to the Q1ASM value

			seq += f"""\n	set_awg_offs	{offset_q1},{offset_q1}""" # Set the offset
			# Since the maximum wait time for an upd_param command is 65535 ns, we will need multiple commands if there are longer pulses than 65535 ns.
			num_full_waits = math.floor(step[1]/65535) # Number of full waits
			remainder = step[1]%65535	# Remaining wait time
			# Adding wait time to the sequence string
			for i in range(num_full_waits):
				seq += f"""\n	upd_param	65535"""
			if remainder != 0:
				seq += f"""\n	upd_param	{remainder}"""
			seq += f"""\n	set_mrk	0"""

		else:
			print("ERROR: module type not supported by make_sequence()\nSee the docstring at the start of the function for supported module types.")
			return None
	
	# Check if we need to loop:
	if iterations > 1:
		seq += f"""\n	loop	R0,@loop"""

	# Set the offset voltage to 0, turn off the marker and stop the sequencer
	seq += f"""\n	set_mrk	{0b0000}\n	set_awg_offs	0,0\n	upd_param	4\n	stop"""

	# Adding all information to a sequence dictionary to be passed to the sequencer
	sequence_dict = {
		"waveforms": {},
		"weights": {},
		"acquisitions": {},
		"program": seq
	}

	return sequence_dict

def connect_rf_output(module:Module, sequencer:int, output_index:int, nco_freq:int, lo_freq:int):
	"""Function that makes a connection to the QCM-RF and sets the NCO and LO frequencies
	to the specified values"""

	# Using eval() allows us to instert the variables into the commands we are trying to play
	eval(f"module.sequencer{sequencer}.connect_out{output_index}(True)") # Connect to the selected output
	eval(f"module.sequencer{sequencer}.mod_en_awg(True)") # Enable modulation of the NCO
	eval(f"module.out{output_index}_lo_en(True)") # Enable modulation of the LO
	eval(f"module.sequencer{sequencer}.nco_freq({nco_freq})") # Set NCO frequency
	eval(f"module.out{output_index}_lo_freq({lo_freq})") # Set LO frequency
	eval(f"module.sequencer{sequencer}.sync_en(True)") # Enable syncing to other sequencers
	return None

def make_input_sequence(input:list, iterations:int = 1, resolution = 300):
	"""Function that takes a list of acquisition instructions and make
	a sequence dictionary with the Q1ASM sequence and acquisitions needed
	in order to do a full acquisition
	
	The acquisition input list will take the following form:
		['name', delay, duration]
	"""

	# Duration of the acquisition
	duration = input[2]

	# If the acquistion is within the time limit of one acquisition.
	if duration <= 16384:
		# Set up the acquisition
		acquisitions = {
			f"{input[0]}": {"num_bins": 1, "index": 0}
		}

		# Initialize the sequence string
		seq = f""""""

		# Check if we need to loop
		if iterations > 1:
			seq += f"""	move	{iterations},R0\n	loop:"""

		# Set up the sequence
		seq += f"""\n	wait_sync	4"""

		delay = int(input[1])
		# If there is a delay for the acquisition start, add a wait command
		if delay != 0:
			# Since the maximum wait time for an upd_param command is 65535 ns, we will need multiple commands if there are longer waits than 65535 ns.
			num_full_waits = math.floor(delay/65535)	# Number of full wait commands
			remainder = delay%65535	# Remaining wait time
			# Adding the wait time to the sequence string
			for i in range(num_full_waits):
				seq += f"""\n	wait	65535"""
			if remainder != 0:
				seq += f"""\n	wait	{remainder}"""
		
		# Add the acquire command
		seq += f"""\n	acquire	0,0,{duration}"""

		# Check if we need to loop
		if iterations > 1:
			seq += f"""\n	loop	R0,@loop"""

		# Stop
		seq += f"""\n	stop"""
	
	else:
		# If the acquisition is more than the time of one acquisition
		num_bins = math.ceil(duration / resolution)
		acquisitions = {
				f"{input[0]}": {"num_bins": num_bins, "index": 0}
			}

		# Set up the acquisition sequence
		seq = f"""		move 		0,R0\n		move		{num_bins},R1\n		wait_sync	4\n		wait		150"""

		delay = int(input[1])
		# If there is a delay for the acquisition start
		if delay != 0:
			# Since the maximum wait time for an upd_param command is 65535 ns, we will need multiple commands if there are longer waits than 65535 ns.
			num_full_waits = math.floor(delay/65535)	# Number of full wait commands
			remainder = delay%65535	# Remaining wait time
			# Adding the wait time to the sequence string
			for i in range(num_full_waits):
				seq += f"""\n	wait	65535"""
			if remainder != 0:
				seq += f"""\n	wait	{remainder}"""

		# Loop and acquire for however long it needs
		seq += f"""\n	loop:\n		acquire		0,R0,{resolution}\n		add			R0,1,R0\n		loop		R1,@loop\n		stop"""

	#print(f"Input sequence:\n{seq}")

	# Add the information to the sequence dictionary
	sequence = {
		"waveforms": {},
		"weights": {},
		"acquisitions": acquisitions,
		"program": seq,
	}

	return sequence

def plot_input(module:Module, sequencer:int, acquisition_name:str, path = 'both', range:list = [0, 10000000000000]):
	module.get_acquisition_status(sequencer) # Wait for the sequencer to stop with a timeout period of one minute.
	module.store_scope_acquisition(sequencer, acquisition_name) # Move acquisition data from temporary memory to acquisition list.
	readout_data = module.get_acquisitions(sequencer) # Get acquisition list from instrument.

	# Find the number of bins to determine what kind of acquistion we are doing.
	num_bins = len(readout_data['acq']['acquisition']['bins']['integration']['path0'])

	if num_bins == 1:
		# If it is a single acquisition with resolution of 1 ns
		data0 = readout_data[acquisition_name]['acquisition']['scope']['path0']['data'] # Extract path 0 data
		data1 = readout_data[acquisition_name]['acquisition']['scope']['path1']['data'] # Extract path 1 data

		# Create plot
		fig, ax = plt.subplots(1, 1, figsize = (14, 4))
		t = np.arange(0, 16384, 1)

		# Plot both paths data
		if path == 0 or path == 'both':
			ax.plot(t[range[0]:range[1]], data0[range[0]:range[1]], alpha = 0.9, label = "Path 0")
		if path == 1 or path == 'both':
			ax.plot(t[range[0]:range[1]], data1[range[0]:range[1]], alpha = 0.9, label = "Path 1")

		# Set titles
		ax.set_title("QRM input")
		ax.set_xlabel("Time [ns]")
		ax.set_ylabel("Input [V]")
		
		# Add a grid to the plot
		ax.grid(ls = '--')

		# Display a legend
		plt.legend()
		plt.show()

	else: 
		# If we are doing a long acquistion (more than 16384 ns), with the data stored in the bins
		# Initialize our resolution variable, to be set later
		resolution = 0

		# Get the resolution from the integration length of the sequencer used for the acquistion
		if sequencer == 0:
			resolution = module.sequencer0.integration_length_acq()
		elif sequencer == 1:
			resolution = module.sequencer1.integration_length_acq()
		elif sequencer == 2:
			resolution = module.sequencer2.integration_length_acq()
		elif sequencer == 3:
			resolution = module.sequencer3.integration_length_acq()
		elif sequencer == 4:
			resolution = module.sequencer4.integration_length_acq()
		elif sequencer == 5:
			resolution = module.sequencer5.integration_length_acq()
		else:
			print("ERROR: sequencer index invalid")
			return None

		print(f"resolution in plot_input: {resolution}")
		data0 = np.array(readout_data['acq']['acquisition']['bins']['integration']['path0']) / resolution # Extract path 0 data
		data1 = np.array(readout_data['acq']['acquisition']['bins']['integration']['path1']) / resolution # Extract path 1 data
		t = np.arange(resolution / 2, resolution * num_bins + 0.1, resolution)

		# Create plot
		fig, ax = plt.subplots(1, 1, figsize = (14, 4))

		# Plot both paths data
		if path == 0 or path == 'both':
			ax.plot(t[range[0]:range[1]], data0[range[0]:range[1]], alpha = 0.9, label = "Path 0")
		if path == 1 or path == 'both':
			ax.plot(t[range[0]:range[1]], data1[range[0]:range[1]], alpha = 0.9, label = "Path 1")

		# Set titles
		ax.set_title("QRM input")
		ax.set_xlabel("Time [ns]")
		ax.set_ylabel("Input [V]")

		# Add a grid to the plot
		ax.grid(ls = '--')

		# Display a legend
		plt.legend()
		plt.show()

	return None

def marker_only_sequence():
	""" Function that makes a sequence for the QCM_RF to only play its marker to the oscilloscope
	"""
	sequence_dict = {
		"waveforms": {},
		"weights": {},
		"acquisitions": {},
		"program": f"""	wait_sync	4\n	set_mrk	{0b1001}\n	upd_param	500\n	set_mrk	{0b0000}\n	upd_param	4\n	stop"""
	}
	return sequence_dict

def connect_marker_only(module:Module, sequencer:int):
	eval(f"module.sequencer{sequencer}.sync_en(True)") # Enable sync with the other sequencers
	return None

def connect_output(module:Module, sequencer:int, output_index:int, path:int):
	""" Function to set up the connection from a sequencer and an output
	"""
	# Determine which path should be used
	path_name = 'I'
	if path == 1:
		path_name = 'Q'
	eval(f"module.sequencer{sequencer}.connect_out{output_index}('{path_name}')") # Connect to the output
	eval(f"module.sequencer{sequencer}.sync_en(True)") # Enable sync with the other sequencers
	return None

def connect_input(module:Module, sequencer:int, input_index:int, path:int, resolution = 300):
	""" Function to set up the connection from a sequencer and an input
	"""
	# Determine the path being used
	path_name = 'I'
	if path == 1:
		path_name = 'Q'
	eval(f"module.sequencer{sequencer}.connect_acq_{path_name}('in{input_index}')")	# Connect to the input
	module.scope_acq_sequencer_select(sequencer) # Select scope mode
	eval(f"module.scope_acq_trigger_mode_path{path}('sequencer')") # Set the scope to trigger off of the sequencer acquire commands
	eval(f"module.sequencer{sequencer}.delete_acquisition_data(all = True)") # Delete the previous acquisition
	eval(f"module.sequencer{sequencer}.integration_length_acq({resolution})") # Set the integration length / resolution
	eval(f"module.scope_acq_avg_mode_en_path{path}(True)") # Enable averaging over many loops
	eval(f"module.sequencer{sequencer}.sync_en(True)") # Enable syncing with other sequencers
	return None

def disconnect_io(module:Module):
	module.disconnect_outputs() # Disconnect the module's outputs
	if module.is_qrm_type:
		module.disconnect_inputs() #  If there are inputs, disconnect the inputs

def sequence_helper_test():
	"""This function is to provide a test that the sequence_helper file 
	has been successfully loaded in the notebook being used"""

	return "test successful"
"""
seqeuence_helper.py		v 1.0

This is a library of useful functions to make Qblox sequencing faster and more user-friendly.

Copy this .py file into the same folder with the notebook you are using, and import the library using:
	import waveform_helper as wh

Created: 		Nov 28, 2024
Last updated: 	Dec 09, 2024
				On firmware:			0.9.2
				On qblox-instruments:	0.14.2	

Author: Kyle MacRobbie
"""

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

		output[name] = {}
		output[name]['data'] = data
		output[name]['index'] = int(specs[name][len(specs[name]) - 1])

	return output

def plot_waveforms(waveforms):
	"""Function that takes a waveform dictionary
	and plots the waveforms"""

	fig, ax = plt.subplots(1, 1, figsize = (14, 4))
	for wave in waveforms:
		ax.plot(waveforms[wave]['data'], label = wave)
	ax.set_title("Waveforms")
	ax.set_xlabel("Time [ns]")
	ax.set_ylabel("Amplitude [a.u.]")
	ax.grid(ls = '--')
	plt.legend()
	plt.show()
	return None

def make_output_sequence(input:list, module:str,  plot = False):
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


	interpreted_module = str(inspect.getframeinfo(inspect.currentframe().f_back)[3][0][0:3])

	if interpreted_module != 'qcm' and interpreted_module != 'qrm':
		print(f"ERROR: module name not recognized ({interpreted_module}). Please name your modules one of the following:\n\t- qrm_module\n\t- qcm_module\n\nIf you are trying to sequence an RF module, please use make_rf_sequence() instead of make_output_sequence().")
		return None

	# Set module range depending on what module is being used.
	module_range = 0
	awg_offs_range = 32767

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

	# Find the total sequence length
	total_len = 0
	for step in input:
		total_len += step[1]

	# If the total length of all the waveforms is less than the length of one acquisition, we use only one acquisition for the highest resolution.
	if total_len <= 16384:
		# Since we can't have a waveform with a magnitude greater than 1, if a ramp spans more than 0.5 V, the funciton will raise an error
		# To rememdy this, any ramp crossing 0 V will be split into two ramps, one going from start to 0 and the other going from 0 to end.
		input_range_corrected = []
		for step in input:
			if step[0] == 'ramp' and ((step[2] > 0 and step[3] < 0) or ((step[2] < 0 and step[3] > 0))):
				# If it is a ramp that crosses 0
				# Find the time that it crosses 0, and split into two waveforms and steps
				ramp_lenght = step[1]
				per = step[2] / (abs(step[2]) + abs(step[3])) # decimal percentage of the amount of ramp time that will have to be spent on the first ramp
				first_length = round(ramp_lenght)*per # Length of the first ramp
				second_length = ramp_lenght - first_length # Length of the second ramp
				first_ramp = ['ramp', first_length, step[2], 0]
				second_ramp = ['ramp', second_length, 0, step[3]]
				input_range_corrected.append(first_ramp)
				input_range_corrected.append(second_ramp)
			else:
				# If it does not cross zero, keep the step as it is
				input_range_corrected.append(step)
		input = input_range_corrected

		# Setting up the waveforms dictionary and the sequence string.
		waveform_specs = {}
		sequence = """	wait_sync	4"""

		# Looping through the input list, adding to the sequence string and waveforms dictionary as needed.
		waveform_index = 0
		temp_str = """"""
		for step in input:
			# Check what type of step it is (square or ramp).
			step_type = step[0]
			step_len = int(step[1])

			if step_type == "square":
				offset = step[2]
				offset_q1 = round((offset/module_range)*awg_offs_range) # Convert to offset to the Q1ASM value
				temp_str = f"""\n	set_awg_offs	{offset_q1},{offset_q1}\n	upd_param	{step_len}"""
			
			elif step_type == "ramp":
				# For a ramp, the offset will first be set to whatever the final voltage of the ramp is
				# then the ramp will be played on top of that offset voltage.
				start = (step[2] - step[3]) / module_range
				end = 0
				waveform_specs[str(waveform_index)] = ['ramp', step_len, start, end, waveform_index]
				new_offset = step[3]
				new_offset_q1 = round((new_offset/module_range)*awg_offs_range) # Convert to offset to the Q1ASM value
				temp_str = f"""\n	set_awg_offs	{new_offset_q1},{new_offset_q1}\n	play	{waveform_index},{waveform_index},{step_len}"""
				waveform_index += 1

			else:
				print("ERROR: step type not supported by make_sequence().\nSee the docstring at the start of the function for supported step types.")

			sequence += temp_str

		# End by resetting the offset to 0 and stopping the sequence
		sequence += """\n	set_awg_offs	0,0\n	upd_param	4\n	stop"""

		waveforms = make_waveforms(waveform_specs)
		if plot == True:
			plot_waveforms(waveforms)

	else:
		# Before defining a resolution, we need to find the total length of all the steps
		duration = 0 
		for step in input:
			duration += step[1]

		num_subpulses = (12288 / 2) - 50	# Making sure we don't pass the 12288 instruction limit for the sequencer
		resolution = round(duration / num_subpulses) # Define the resolution based on how many instructions we can give

		# Values to adjust for the module being used
		module_range = 0.5
		if module == 'qcm':
			module_range = 2.5
		awg_offs_range = 32767

		sequence_play = """"""

		for step in input:
			if step[0] == 'ramp':
				start_voltage = step[2]
				end_voltage = step[3]
				start_offset_q1 = round((start_voltage / module_range) * awg_offs_range) # Convert to offset to the Q1ASM value
				end_offset_q1 = round((end_voltage / module_range) * awg_offs_range) # Convert to offset to the Q1ASM value
				# The number of steps in the ramp will be proportional to how many subpulses are being used on it
				step_size_q1 = (((end_voltage - start_voltage) / round(num_subpulses*(step[1]/duration))) / module_range) * awg_offs_range
				offsets_q1 = np.round(np.arange(start_offset_q1 + step_size_q1, end_offset_q1 + step_size_q1, step_size_q1))
				# Loop through the steps
				for offset in offsets_q1:
					sequence_play += f"""\n	set_awg_offs	{int(offset)},{int(offset)}\n	upd_param	{int(resolution)}"""

			else:
				voltage = step[2]
				offset_q1 = round((voltage / module_range) * awg_offs_range)
				offsets_q1 = np.round(np.zeros(round(num_subpulses*(step[1]/duration))) + offset_q1)
				# If its square, just play the same offset for however many subpulses were calculated for this step
				for offset in offsets_q1:
					sequence_play += f"""\n	set_awg_offs	{int(offset)},{int(offset)}\n	upd_param	{int(resolution)}"""

		sequence = """\n	wait_sync	4""" + sequence_play + f"""\n	set_awg_offs	0,0\n	upd_param	4\n	stop"""
		waveforms = {}

	# print(f"Sequence:\n{sequence}")

	sequence_dict = {
		"waveforms": waveforms,
		"weights": {},
		"acquisitions": {},
		"program": sequence
	}

	return sequence_dict

def make_rf_sequence(input:list, module:Module, marker, plot = False):
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

	waveforms = {}
	waveform_index = 0

	seq = f"""	wait_sync	4"""

	if marker == 0:
		seq += f"""\n	set_mrk	{0b1001}"""
	elif marker == 1:
		seq += f"""\n	set_mrk	{0b0110}"""
	elif marker == 'both':
		seq == f"""\n	set_mrk {0b1111}"""
	else:
		print("ERROR: marker type not supported. Supported arguements are:\n- 0\n- 1\n- 'both'")

	for step in input:
		if step[0] == 'wait':
			seq += f"""\n	wait	{step[1]}"""
		elif step[0] == 'square':
			waveforms[str(waveform_index)] = {}
			waveforms[str(waveform_index)]['data'] = [2*step[2] for i in range(0, step[1])]
			waveforms[str(waveform_index)]['index'] = waveform_index
			seq += f"""\n	play	{waveform_index},{waveform_index},{step[1]}"""
			waveform_index += 1
		else:
			print("ERROR: module type not supported by make_sequence()\nSee the docstring at the start of the function for supported module types.")
			return None
	
	seq += f"""\n	set_mrk	{0b0000}\n	stop"""

	print(seq)

	sequence_dict = {
		"waveforms": waveforms,
		"weights": {},
		"acquisitions": {},
		"program": seq
	}

	if plot == True:
		plot_waveforms(waveforms)

	return sequence_dict

def connect_rf_output(module:Module, seuquencer:int, output_index:int, nco_freq:int, lo_freq:int):
	"""Function that makes a connection to the QCM-RF and sets the NCO and LO frequencies
	to the specified values"""
	module.disconnect_outputs()
	module.disconnect_outputs()
	eval(f"module.sequencer{seuquencer}.connect_out{output_index}(True)")
	eval(f"module.sequencer{seuquencer}.mod_en_awg(True)")
	eval(f"module.out{output_index}_lo_en(True)")
	eval(f"module.sequencer{seuquencer}.nco_freq({nco_freq})")
	eval(f"module.out{output_index}_lo_freq({lo_freq})")
	eval(f"module.sequencer{seuquencer}.sync_en(True)")
	return None

def make_input_sequence(input:list):
	"""Function that takes a list of acquisition instructions and make
	a sequence dictionary with the Q1ASM sequence and acquisitions needed
	in order to do a full acquisition
	
	The acquisition input list will take the following form:
		['name', delay, duration]
	"""

	duration = input[2]

	# If the acquistion is within the time limit of one acquisition.
	if duration <= 16384:
		# Set up the acquisition
		acquisitions = {
			f"{input[0]}": {"num_bins": 1, "index": 0}
		}

		# Set up the sequence
		seq = f"""	wait_sync	4"""

		delay = int(input[1])
		# If there is a delay for the acquisition start, add a wait command
		if delay != 0:
			seq += f"""\n	wait	{delay}"""
		
		# Add the acquire command
		seq += f"""\n	acquire	0,0,{duration}\n	stop"""
	
	else:
		# If the acquisition is more than the time of one acquisition
		resolution = 250 # ns
		num_bins = math.ceil(duration / resolution)
		acquisitions = {
				f"{input[0]}": {"num_bins": num_bins, "index": 0}
			}

		# Set up the acquisition sequence
		seq = f"""		move 		0,R0\n		move		{num_bins},R1\n		wait_sync	4\n		wait		150"""

		delay = int(input[1])
		# If there is a delay for the acquisition start
		if delay != 0:
			seq += f"""\n		wait	{delay}"""

		# Loop and acquire for however long it needs
		seq += f"""\n	loop:\n		acquire		0,R0,{resolution}\n		add			R0,1,R0\n		loop		R1,@loop\n		stop"""

	# Add the information to the sequence dictionary
	sequence = {
		"waveforms": {},
		"weights": {},
		"acquisitions": acquisitions,
		"program": seq,
	}

	return sequence

def plot_input(module:Module, sequencer:int, acquisition_name:str):
	module.get_acquisition_status(sequencer) # Wait for the sequencer to stop with a timeout period of one minute.
	module.store_scope_acquisition(sequencer, acquisition_name) # Move acquisition data from temporary memory to acquisition list.
	readout_data = module.get_acquisitions(sequencer) # Get acquisition list from instrument.

	num_bins = len(readout_data['acq']['acquisition']['bins']['integration']['path0'])

	if num_bins == 1:
		# If it is one acquisition with resolution of 1 ns
		data0 = readout_data[acquisition_name]['acquisition']['scope']['path0']['data']
		data1 = readout_data[acquisition_name]['acquisition']['scope']['path1']['data']
		fig, ax = plt.subplots(1, 1, figsize = (14, 4))
		ax.plot(data0, alpha = 0.9, label = "Path 0")
		ax.plot(data1, alpha = 0.9, label = "Path 1")
		ax.set_title("QRM input")
		ax.set_xlabel("Time [ns]")
		ax.set_ylabel("Input [V]")
		ax.grid(ls = '--')
		plt.legend()
		plt.show()

	else: 
		# If it is longer than one acquisition and have a resolution of 250 ns
		resolution = 250
		data0 = np.array(readout_data['acq']['acquisition']['bins']['integration']['path0']) / resolution
		data1 = np.array(readout_data['acq']['acquisition']['bins']['integration']['path1']) / resolution
		t = np.arange(resolution / 2, resolution * num_bins + 0.1, resolution)
		fig, ax = plt.subplots(1, 1, figsize = (14, 4))
		ax.plot(t, data0, alpha = 0.9, label = "Path 0")
		ax.plot(t, data1, alpha = 0.9, label = "Path 1")
		ax.set_title("QRM input")
		ax.set_xlabel("Time [ns]")
		ax.set_ylabel("Input [V]")
		ax.grid(ls = '--')
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

def connect_output(module:Module, sequencer:int, output_index:int, path:int):
	""" Function to set up the connection from a sequencer and an output
	"""
	module.disconnect_outputs()
	path_name = 'I'
	if path == 1:
		path_name = 'Q'
	eval(f"module.sequencer{sequencer}.connect_out{output_index}('{path_name}')")
	eval(f"module.sequencer{sequencer}.sync_en(True)")
	return None

def connect_input(module:Module, sequencer:int, input_index:int, path:int):
	""" Function to set up the connection from a sequencer and an output
	"""
	module.disconnect_inputs()
	path_name = 'I'
	if path == 1:
		path_name = 'Q'
	eval(f"module.sequencer{sequencer}.connect_acq_{path_name}('in{input_index}')")
	module.scope_acq_sequencer_select(sequencer)
	eval(f"module.scope_acq_trigger_mode_path{path}('sequencer')")
	eval(f"module.sequencer{sequencer}.delete_acquisition_data(all = True)")
	eval(f"module.sequencer{sequencer}.integration_length_acq(220)")
	eval(f"module.sequencer{sequencer}.sync_en(True)")

	return None

def waveform_helper_test():
	"""This function is to provide a test that the waveform_helper file 
	has been successfully loaded in the notebook being used"""

	return "test successful"
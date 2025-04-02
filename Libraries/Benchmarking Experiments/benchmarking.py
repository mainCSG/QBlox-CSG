"""
benchmarking.py V 1.0

This library will be updated periodically when benchmarking experiments with Qblox are developed. These functions will
be designed to streamline the process of preparing a Quantum Dot device for experiments.

You may also use this file in tandem with the benchmarking.ipynb to get a good understanding of how this library works.

Created:		Feb 06, 2025
Last Updated:	Feb 06, 2025
Tested:         Feb 06, 2025
				On firmware:			0.9.2
				On qblox-instruments:	0.14.2	

Author: Ben Van Osch

"""

# Imports
import scipy
import math
import matplotlib.pyplot as plt
from qblox_instruments.qcodes_drivers.module import Module
import numpy as np
import inspect
import sys
sys.path.append(r"C:\\Users\\BaughLaflamme\\Desktop\\Qblox Master Folder\\Cluster\\Libraries\\Qblox Sequence Helpers")
import sequence_heplerV2 as sh
import time

def sweep_2d(num_steps, stepsize, sweep_length, start_point, end_point):

	"""
	This function allows the user to create a 2D Voltage Sweep with minimal interaction with Q1ASM and the Qblox cluster.

	The function takes inputs:

	num_steps:    The number of voltage steps in the sweep
	stepsize:     The stepsize in volts (e.g. if you wanted steps of 10 mV then you would input 10e-3)
	sweep_length: The duration of the 
	start_point:  The starting voltage for the sweeps
	end_point:    The ending voltage for the sweeps
	
	"""

	# First, we define an empty output seqeunce, basically an empty list. We also define our voltage sweep parameters

	output_seq_0 = []

	num_list = range(0,num_steps)

	# Now, we define our first output sequence as sequential ramps one after the other

	output_seq_0.append(['ramp', sweep_length, start_point, end_point])

	output_seq_0 *= num_steps

	# Now, we need to define our second output sequence 

	output_seq_1 = []

	for i, val in enumerate(num_list):
		output_seq_1.append(['square', sweep_length, stepsize*val])

	# Now, we disconnect any prexisting connections

	sh.disconnect_io(qcm_module)
	sh.disconnect_io(qrm_module)

	# Now, we upload our sequences to the modules and specify sequencers

	qcm_module.sequencer0.sequence(sh.make_output_sequence(output_seq_0, module = "qcm"))
	qcm_module.sequencer1.sequence(sh.make_output_sequence(output_seq_1, module = "qcm"))
	qrm_module.sequencer0.sequence(sh.make_input_sequence(input_seq_0))

	# Now, we connect the modules to the sequencers

	qcm_module.sequencer0.connect_out0("I")
	qcm_module.sequencer1.connect_out1("I")
	sh.connect_input(module = qrm_module, sequencer = 0, input_index = 0, path = 0)

	# Then, we enable the sync protocol for all sequencers

	qcm_module.sequencer0.sync_en(True)
	qcm_module.sequencer1.sync_en(True)
	qrm_module.sequencer0.sync_en(True)

	# Here we arm the sequencers

	qcm_module.arm_sequencer(0)
	qcm_module.arm_sequencer(1)
	qrm_module.arm_sequencer(0)

	# This next step runs the sequences we loaded

	cluster.start_sequencer()

	# Then, we stop the sequencers

	qcm_module.stop_sequencer(0)
	qcm_module.stop_sequencer(1)
	qrm_module.stop_sequencer(0)


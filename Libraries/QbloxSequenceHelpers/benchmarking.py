"""
benchmarking.py V 1.0

This library will be updated periodically when benchmarking experiments with Qblox are developed. These methods will
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
from __future__ import annotations 
from datetime import datetime
import matplotlib.pyplot as plt
import pyvisa
import os
import numpy as np
from typing import TYPE_CHECKING, Callable
from qcodes.instrument import find_or_create_instrument
from qblox_instruments import Cluster, ClusterType
if TYPE_CHECKING:
    from qblox_instruments.qcodes_drivers.module import Module
import sys
sys.path.append(r"C:\\Users\\coher\\Documents\\GitHub\\QBlox-CSG\\Libraries\\Qblox Sequence Helpers")
import sequence_helperV2 as sh
import benchmarking as bm
import time


def get_connected_modules(cluster: Cluster, filter_fn: Callable | None = None) -> dict[int, Module]:
			def checked_filter_fn(mod: ClusterType) -> bool:
				if filter_fn is not None:
					return filter_fn(mod)
				return True
			return {
				mod.slot_idx: mod for mod in cluster.modules if mod.present() and checked_filter_fn(mod)
			}

class QbloxExperiment:

	def __init__(self):

		self.cluster_ip = "129.97.9.55"
		self.cluster_name = "cluster0"
		self.cluster = find_or_create_instrument(
			Cluster,
			recreate=True,
			name=self.cluster_name,
			identifier=self.cluster_ip,
			dummy_cfg=(
				{
					2: ClusterType.CLUSTER_QCM,
					4: ClusterType.CLUSTER_QRM,
					6: ClusterType.CLUSTER_QCM_RF,
				}
				if self.cluster_ip is None
				else None
			),
		)
		self.cluster.led_brightness('medium') # Sets LED brightness on the modules. Options are 'low', 'medium' and 'high'
		# Get modules, and connect to the QRM
		
		modules = get_connected_modules(self.cluster)
		self.module = list(modules.values())[0]
		self.cluster.reset()

		print(modules)
		print(self.cluster.get_system_status())
		
		self.qcm_module = modules[2]
		self.qrm_module = modules[4]
		self.rf_module = modules[6]

		"""TODO Add functionality that automatically detects and informs the user of which modules are connected 
		to which slots, rather than the slots being predefined. Also add error if there are any issues with modules connecting
		"""

	def run_1D_trace(self, num_steps, length_per_point, start_point: float, end_point: float, acq_sequencer: int, acquisition_name: str, acquisition_delay = 0, resolution = 300, repeats = 1, save_path = r'C:\\Users\\coher\\Desktop', plot = False):

		"""
		This function allows the user to create a 1D Voltage Trace with minimal interaction with Q1ASM and the Qblox cluster.

		The function takes inputs:

		num_steps:         The number of voltage steps in the sweep for both gates
		length_per_point:  The full duration of a single point in nanoseconds
		start_point:       The starting voltage for the trace in volts
		end_point:         The ending voltages for the trace in volts
		acq_sequencer:     The label of the sequencer being used for acquisition
		acquisition_name:  The name given to the acquisition
		acquisition_delay: The amount of time before an acquisition starts in nanoseconds 
		plot:              If True, run_2D_sweep() will create a heat map of the data; Set to False by default 
						   and will output a voltage sweep through the qcm into a device, and will acquire a signal from the device, which will
						   then be plotted against the input voltage. 
							
		"""

		# Before anything, we have to set up the data variable to hold the data from each repeat

		dataI = []

		# First, we define an empty output seqeunce, basically an empty list. We also define our voltage sweep parameters

		output_seq_0 = []

		seq_time = 0

		output_0_list = np.linspace(start_point, end_point, num_steps)

		# print(output_0_list)

		for i in output_0_list:
			output_seq_0.append(['square', length_per_point, i])
		
		seq_time += length_per_point*num_steps

		# Now, we define our input sequence.

		input_seq_0 = [acquisition_name, acquisition_delay, length_per_point*num_steps]

		# Now, we disconnect any prexsisting connections

		qcm_module = self.qcm_module
		qrm_module = self.qrm_module
		rf_module = self.rf_module
		cluster = self.cluster

		# TODO add error message if there are mislabeled modules

		sh.disconnect_io(qcm_module)
		sh.disconnect_io(qrm_module)

		I_offset, Q_offset = sh.acquire_scope_and_calc_offsets(qrm_module)

		sh.disconnect_io(qcm_module)
		sh.disconnect_io(qrm_module)
		sh.disconnect_io(rf_module)

		# Now, we upload our sequences to the modules and specify sequencers		

		qcm_module.sequencer0.sequence(sh.make_output_sequence(output_seq_0, module = "qcm", iterations = repeats))
		qrm_module.sequencer0.sequence(sh.make_input_sequence(input_seq_0, resolution = resolution)[0])
		rf_module.sequencer0.sequence(sh.marker_only_sequence())

		seq_time += 150 # Accounting for ToF

		# Now, we connect the modules to the sequencers

		qcm_module.sequencer0.connect_out0("I")
		sh.connect_input(module = qrm_module, sequencer = acq_sequencer, input_index = 0, path = 0, resolution = resolution)
		sh.connect_marker_only(module = rf_module, sequencer = 0)

		""" 
		The QRM has a built-in amplifier that automatically amplifies any imput signal by 6 dB. In the following, 
		we are simply offsetting that amplification. There's also a DC offset, which we account for here.
		
		"""
		input_gain = -6

		qrm_module.in0_gain(input_gain)
		qrm_module.in1_gain(input_gain)
		
		if abs(I_offset) > 0.02:
			qrm_module.in0_offset(-0.0)
		else:
			qrm_module.in0_offset(-I_offset)

		qrm_module.in1_offset(-Q_offset)

		# Then, we enable the sync protocol for all sequencers

		qcm_module.sequencer0.sync_en(True)
		qrm_module.sequencer0.sync_en(True)
		rf_module.sequencer0.sync_en(True)

		# Here we arm the sequencers

		qcm_module.arm_sequencer(0)
		qrm_module.arm_sequencer(0)
		rf_module.arm_sequencer(0)

		# This next step runs the sequences we loaded

		cluster.start_sequencer()

		# Convert time from seconds to nanoseconds

		seq_time /= 1e9

		time.sleep(seq_time)

		# Then, we stop the sequencers

		qcm_module.stop_sequencer(0)
		qrm_module.stop_sequencer(0)
		rf_module.stop_sequencer(0)

		# If plot is True, then this part of the method will create a heat map as a function of the voltages

		if plot:
			
			sh.plot_input(module = qrm_module, sequencer = acq_sequencer, acquisition_name = acquisition_name)

			X = np.asarray(output_0_list)

			# This section retrieves the data from the acquisition

			qrm_module.get_acquisition_status(acq_sequencer) # Wait for the sequencer to stop with a timeout period of one minute.
			qrm_module.store_scope_acquisition(acq_sequencer, acquisition_name) # Move acquisition data from temporary memory to acquisition list.
			readout_data = qrm_module.get_acquisitions(acq_sequencer) # Get acquisition list from instrument.

			if acq_sequencer == 0:
				resolution = qrm_module.sequencer0.integration_length_acq()
			elif acq_sequencer == 1:
				resolution = qrm_module.sequencer1.integration_length_acq()
			elif acq_sequencer == 2:
				resolution = qrm_module.sequencer2.integration_length_acq()
			elif acq_sequencer == 3:
				resolution = qrm_module.sequencer3.integration_length_acq()
			elif acq_sequencer == 4:
				resolution = qrm_module.sequencer4.integration_length_acq()
			elif acq_sequencer == 5:
				resolution = qrm_module.sequencer5.integration_length_acq()
			else:
				print("ERROR: sequencer index invalid")
				return None

			# Find the number of bins to determine what kind of acquistion we are doing.
			num_bins = len(readout_data[acquisition_name]['acquisition']['bins']['integration']['path0'])

			# print("number of bins: ",num_bins)

			if num_bins == 1:

				# print(f"resolution in plot_input: {resolution}")
				# If it is a single acquisition with resolution of 1 ns
				data0 = readout_data[acquisition_name]['acquisition']['scope']['path0']['data'] # Extract path 0 data

			else:
				
				repeat_num = sh.make_input_sequence(input_seq_0, resolution = resolution)[1]

				# print(f"resolution in plot_input: {resolution}")

				data0 = np.array(readout_data[acquisition_name]['acquisition']['bins']['integration']['path0']) / resolution # Extract path 0 data

			#print(data0)

			#print(data0.shape)

			# Now, we add this sweeps data to the data list

			dataI.append(data0)

		# Resets the connection to the cluster. If not done, the offsets will be incorrect when playing another sequence.

		cluster.reset()

		for data0 in dataI:

			# Now, we have to reshape the data to be the same shape as X and Y

			if data0.shape[0] % (len(output_0_list)) != 0:
				raise ValueError(f"The amount of data taken is unable to be shaped into {np.shape(X)}")
				
			data0_reshaped = data0.reshape(X.shape[0], repeat_num)

			data0_final = data0_reshaped.mean(axis=1) * repeat_num

			#data0_final = avg_data0.reshape(X.shape[0],X.shape[1])

			# Now, we save the data to a csv file

			save_data = []

			for i, x in enumerate(output_0_list):
				save_data.append([x, data0_final[i]])

			experiment_time = datetime.now()

			timestamp = experiment_time.strftime('%Y-%m-%d_%H-%M%S')
			
			filename = f"Qblox_Measurement_{timestamp}.csv"

			full_path = os.path.join(save_path, filename)

			np.savetxt(full_path ,save_data, delimiter = ',', fmt = '%s', header = 'QCM Output 1, QCM Output 2, QRM Input Path Q, QRM Input Path I', comments = '')

		return None

	def run_2D_sweep(self, num_steps, outer_sweep_length, start_points: list, end_points: list, acq_sequencer: int, acquisition_name: str, acquisition_delay = 0, resolution = 300, play_repeats = 1, save_path = r'C:\\Users\\coher\\Desktop', plot = False):

		"""
		This function allows the user to create a 2D Voltage Sweep with minimal interaction with Q1ASM and the Qblox cluster.

		The function takes inputs:

		num_steps:          The number of voltage steps in the sweep for both gates
		outer_sweep_length: The full duration of a single sweep of the outer loop in nanoseconds
		start_points:       The starting voltages for the inner and outer sweeps in volts. Input is a list
		end_points:         The ending voltages for the inner and outer sweeps in volts. Input is a list
		acq_sequencer:      The label of the sequencer being used for acquisition
		acquisition_name:   The name given to the acquisition
		acquisition_delay:  The amount of time before an acquisition starts in nanoseconds
		plot:               If True, run_2D_sweep() will create a heat map of the data; Set to False by default 
							and will output a voltage sweep through the qcm into a device, and will acquire a signal from the device, which will
							then be plotted against the input voltages. 
		
		"""

		# Before anything, we have to set up the data variable to hold the data from each repeat

		dataI = []
		dataQ = []



		for i in range(play_repeats):

			# First, we define an empty output seqeunce and our voltage sweep parameters

			output_seq_0 = []

			seq_time = 0

			output_0_list = np.linspace(start_points[0], end_points[0], num_steps)

			# print(output_0_list)

			for i in output_0_list:
				output_seq_0.append(['square', outer_sweep_length/num_steps, i])

			# Now, we need to define our second output sequence 

			output_seq_1 = []

			output_1_list = np.linspace(start_points[1], end_points[1], num_steps)

			# print(output_1_list)

			for i in output_1_list:
				output_seq_1.append(['square', outer_sweep_length, i])

			seq_time += outer_sweep_length*num_steps # Accounting for length of the sequence

			# Finally, we define our input sequence

			input_seq_0 = [acquisition_name, acquisition_delay, outer_sweep_length*num_steps]

			# Now, we disconnect any prexisting connections

			qcm_module = self.qcm_module
			qrm_module = self.qrm_module
			cluster = self.cluster

			# TODO add error message if there are mislabeled modules

			sh.disconnect_io(qcm_module)
			sh.disconnect_io(qrm_module)

			I_offset, Q_offset = sh.acquire_scope_and_calc_offsets(qrm_module)

			sh.disconnect_io(qcm_module)
			sh.disconnect_io(qrm_module)

			# Now, we upload our sequences to the modules and specify sequencers		

			qcm_module.sequencer0.sequence(sh.make_output_sequence(output_seq_0, module = "qcm", iterations = num_steps))
			qcm_module.sequencer1.sequence(sh.make_output_sequence(output_seq_1, module = "qcm"))
			qrm_module.sequencer0.sequence(sh.make_input_sequence(input_seq_0, resolution = resolution)[0])

			seq_time += 150 # Accounting for ToF

			# Now, we connect the modules to the sequencers

			qcm_module.sequencer0.connect_out0("I")
			qcm_module.sequencer1.connect_out1("I")
			sh.connect_input(module = qrm_module, sequencer = acq_sequencer, input_index = 0, path = 0, resolution = resolution)

			""" 
			The QRM has a built-in amplifier that automatically amplifies any imput signal by 6 dB. In the following, 
			we are simply offsetting that amplification. There's also a DC offset, which we account for here.
			
			"""
			input_gain = -6

			qrm_module.in0_gain(input_gain)
			qrm_module.in1_gain(input_gain)
			
			if abs(I_offset) > 0.02:
				qrm_module.in0_offset(-0.02)
			else:
				qrm_module.in0_offset(-I_offset)

			qrm_module.in1_offset(-Q_offset)

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

			# Convert time from seconds to nanoseconds

			seq_time /= 1e9

			time.sleep(seq_time)

			# Then, we stop the sequencers

			qcm_module.stop_sequencer(0)
			qcm_module.stop_sequencer(1)
			qrm_module.stop_sequencer(0)


			# If plot is True, then this part of the method will create a heat map as a function of the voltages

			if plot:
			
			# This section constructs both axes for the heat map

				X, Y = np.meshgrid(output_0_list, output_1_list)
				# print(np.shape(X))

			# This section retrieves the data from the acquisition

				qrm_module.get_acquisition_status(acq_sequencer) # Wait for the sequencer to stop with a timeout period of one minute.
				qrm_module.store_scope_acquisition(acq_sequencer, acquisition_name) # Move acquisition data from temporary memory to acquisition list.
				readout_data = qrm_module.get_acquisitions(acq_sequencer) # Get acquisition list from instrument.

				if acq_sequencer == 0:
					resolution = qrm_module.sequencer0.integration_length_acq()
				elif acq_sequencer == 1:
					resolution = qrm_module.sequencer1.integration_length_acq()
				elif acq_sequencer == 2:
					resolution = qrm_module.sequencer2.integration_length_acq()
				elif acq_sequencer == 3:
					resolution = qrm_module.sequencer3.integration_length_acq()
				elif acq_sequencer == 4:
					resolution = qrm_module.sequencer4.integration_length_acq()
				elif acq_sequencer == 5:
					resolution = qrm_module.sequencer5.integration_length_acq()
				else:
					print("ERROR: sequencer index invalid")
					return None

				# Find the number of bins to determine what kind of acquistion we are doing.
				num_bins = len(readout_data[acquisition_name]['acquisition']['bins']['integration']['path0'])

				# print("number of bins: ",num_bins)

				if num_bins == 1:

					# print(f"resolution in plot_input: {resolution}")
					# If it is a single acquisition with resolution of 1 ns
					data0 = readout_data[acquisition_name]['acquisition']['scope']['path0']['data'] # Extract path 0 data
					data1 = readout_data[acquisition_name]['acquisition']['scope']['path1']['data'] # Extract path 1 data

				else:
					
					repeat_num = sh.make_input_sequence(input_seq_0, resolution = resolution)[1]

					# print(f"resolution in plot_input: {resolution}")

					data0 = np.array(readout_data[acquisition_name]['acquisition']['bins']['integration']['path0']) / resolution # Extract path 0 data
					data1 = np.array(readout_data[acquisition_name]['acquisition']['bins']['integration']['path1']) / resolution # Extract path 1 data

				#print(data0)

				#print(data0.shape)

				# Now, we add this sweeps data to the data list

				dataI.append(data0)
				dataQ.append(data1)

			# Now, we reset our connection to the cluster

			cluster.reset()

		for data0, data1 in zip(dataI,dataQ):

			# Now, we have to reshape the data to be the same shape as X and Y

			if data0.shape[0] % (len(output_0_list)*len(output_1_list)) != 0:
				raise ValueError(f"The amount of data taken is unable to be shaped into {np.shape(X)}")
				
			data0_reshaped = data0.reshape(X.shape[0]*X.shape[1], repeat_num)

			avg_data0 = data0_reshaped.mean(axis=1) * repeat_num

			data0_final = avg_data0.reshape(X.shape[0],X.shape[1])

			if data1.shape[0] % (len(output_0_list)*len(output_1_list)) != 0:
				raise ValueError(f"The amount of data taken is unable to be shaped into {np.shape(Y)}")
				
			data1_reshaped = data1.reshape(Y.shape[0]*Y.shape[1], repeat_num)

			avg_data1 = data1_reshaped.mean(axis=1) * repeat_num

			data1_final = avg_data1.reshape(Y.shape[0],Y.shape[1])

			# Now, we save the data to a csv file

			save_data = []

			for i, y in enumerate(output_1_list):
				for j, x in enumerate(output_0_list):
					save_data.append([x, y, data0_final[i, j], data1_final[i, j]])

			experiment_time = datetime.now()

			timestamp = experiment_time.strftime('%Y-%m-%d_%H-%M%S')
			
			filename = f"Qblox_Measurement_{timestamp}.csv"

			full_path = os.path.join(save_path, filename)

			np.savetxt(full_path ,save_data, delimiter = ',', fmt = '%s', header = 'QCM Output 1, QCM Output 2, QRM Input Path Q, QRM Input Path I', comments = '')

			# TODO add error if data is not the same shape as X and Y

			np.set_printoptions(threshold=np.inf)

			# print(X)

			# Plot the heatmap(s)

			fig, ax = plt.subplots(1, 2, figsize = (15, 10))

			# Heatmap of Path 0

			plot0 = ax[0].pcolormesh(X, Y, data0_final, cmap = 'viridis', shading = 'auto')
			fig.colorbar(plot0, ax = ax[0], label = 'Path 0')
			ax[0].set_title('Heatmap of Path 0')
			ax[0].set_xlabel('V1')
			ax[0].set_ylabel('V2')


			# Heatmap of Path 1

			plot1 = ax[1].pcolormesh(X, Y, data1_final, cmap = 'viridis', shading = 'auto')
			fig.colorbar(plot1, ax = ax[1], label = 'Path 1')
			ax[1].set_title('Heatmap of Path 1')
			ax[1].set_xlabel('V1')
			ax[1].set_ylabel('V2')

			plt.show()
				
		print(qrm_module.get_sequencer_status(0))
		print(qrm_module.get_acquisition_status(0))
		print(qrm_module.get_assembler_status())



		return None



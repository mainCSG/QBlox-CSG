The Qblox Tutorials folder contains the tutorials pulled from the Qblox website. Each tutorial is in its own folder, accompanied by 
a text document with information about if/when the tutorial ran/tested, and what versions of qblox-instruments and firmware it was
tested on. 

I (Kyle) would personally recommend going through the tutorials in the following order, to get a grasp on using the Cluster
and its modules. Note that I'm basing this on what was useful to me, but you may have a different experience if you are doing 
different experiments.

QRM
	- basic sequencing
	- binned acquisition
		One note about this tutorial, this one confused me at first. Basically you're just reading input noise
		and binning the data. Binning just means that you take an acquisition, integrate (sum) the acquisition data over whatever
		length you specify, and storing that number in a bin. A bin simply just holds a number. This loops many times in Q1ASM, one
		loop for each bin, until all the bins have a number in them. Since we integrated (summed) over the data, you need to
		divide by the integration legnth to get the average value of that acquisition.
		Also note that the time given in the acquire Q1ASM command is not necessarily the acquisition time, but rather the minimum
		acquisition time. This means for the final acquisition, there is no other acquisition to stop it, so it will run until
		the maximum acuqistion time (16384 ns) is met. The scope data that you plot at the end of the data is only the last acquisition
		you took, since each time a new acquisition happens, the old scope data is deleted. This is why you get 16384 ns of data
		when you plot at the end, instead of just the time that you selected.
	- scope acquisition
		the part on hardware averaging is important, this lets you run the same sequence many times and get back the average input of
		all the runs.
	- charaterizing input offset
	- continuous waveform mode
	- numerically controlled oscillator
		Just do this to see how the Q1ASM and python commands for the NCO work. The sweeping and results I found hard to follow along
		with and not very useful in the long run. If you need to do fast frequency sweeps in the future it could be good to refer to
		though.

QCM-RF 
	- basic sequencing
	- manual mixer calibration
	- in-situ mixer calibration
		Note for the mixer calibration tutorials, you will need to get your hands on a spectrum analyzer. We borrowed one from RAC 2
		in order to do these tutorials.
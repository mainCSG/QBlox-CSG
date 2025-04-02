This folder is for tests of the QCM-RF phase testing.
The notebook is the file used to play the sequence and collect the data.

The conclusion that we came to is that each time you start a sequence by calling start_sequencer() in python, the LO takes a random phase.
However, over each loop in Q1ASM, the phase is consistent. This is shown in the images in this folder.
100 MHz 1 iteration.png and 100 MHz 1000 iterations.png show that the amplitude does not decrease when playing 1000 time and averaging
by looping in Q1ASM. If the phase was random each time it looped and played in Q1ASM, this would have averaged to 0. Therefore, it is
not random.

two_pulses_180_offs.png shows two pulses played as a part of the same sequence, set to be 180 degrees offset of each other.
Zooming in on the start of each pulse, it can clearly be seen that the phase has be set as was expected with the two being
opposites of each other. 
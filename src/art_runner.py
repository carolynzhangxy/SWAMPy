import shutil
import subprocess
import glob
import os
from os.path import basename, join
from io import StringIO
import numpy as np
from contextlib import contextmanager
import string
import logging


class ArtIllumina:

    def __init__(self, outpath, output_filename_prefix, read_length, seq_sys, verbose,temp, nreads):
        self.outpath = outpath
        self.output_filename_prefix = output_filename_prefix
        self.read_length = read_length
        self.seq_sys = seq_sys
        self.verbose=verbose
        self.temp=temp
        self.nreads=nreads

    def run_once(self, infile, n_reads, out_prefix, rnd_seed):

        op = subprocess.run([
            "art_illumina", 
            "--amplicon",
            #"--quiet",
            "--paired",
            "--rndSeed", str(rnd_seed),
            "--noALN",
            "--maskN", str(0), 
            "--seqSys", self.seq_sys, #"MSv3"
            "--in", infile,
            "--len", str(self.read_length),
            "--rcount", str(n_reads),
            "--out", out_prefix,

            "--minQ", str(30),
            "--maxQ", str(30),
            # "--insRate", str(0),     # Set insert rate to 0
	        # "--insRate2", str(0),    # Set insert rate to 0
            # "--delRate", str(0),     # Set deletion rate to 0
            # "--delRate2", str(0),    # Set deletion rate to 0
            # "--errfree",

        ], capture_output=True)

        message_lines = op.stdout.decode("ASCII").split("\n")[-4:-2]
        warning = op.stderr.decode("ASCII")
        if self.verbose:
            for line in message_lines:
                logging.info("art_illumina: " + line)
        if warning != "Warning: your simulation will not output any ALN or SAM file with your parameter settings!\n":
            logging.warning(warning)

        

    def run(self, amplicons, n_reads):

        params = zip(amplicons, n_reads)

        for a, n in params:
            
            short_name = ".".join(basename(a).split(".")[:-1])
            
            if self.verbose:
                logging.info(f"Starting on file {short_name}.fasta with {n} reads")

            self.run_once(a, n, join(self.temp,"tmp.sms.")+short_name+".", np.random.randint(2 ** 63))


        all_r1_files = sorted([x for x in glob.glob(join(self.temp,"tmp.sms.*")) if x[-4:] == "1.fq"])
        all_r2_files = sorted([x for x in glob.glob(join(self.temp,"tmp.sms.*")) if x[-4:] == "2.fq"])

        with open(join(self.temp,"tmp.sms.all_files_unshuffled1.fastq"), "w") as all_r1:
            for r1 in all_r1_files:
                with open(r1, "r") as r1fh:
                    shutil.copyfileobj(r1fh, all_r1)
        
        with open(join(self.temp,"tmp.sms.all_files_unshuffled2.fastq"), "w") as all_r2:
            for r2 in all_r2_files:
                with open(r2, "r") as r2fh:
                    shutil.copyfileobj(r2fh, all_r2)

        logging.info("Creating random data for shuffle.")
        with open(join(self.temp,"tmp.sms.random_data"), "w") as random_data:
            ALPHABET = np.array(list(string.ascii_lowercase))
            random_data.write("".join(np.random.choice(ALPHABET, size=max(5000000, int(2.5*self.nreads)))))

        # shuffle the fastq's so that the reads are in a random order. 
        shuffle_fastq_file(join(self.temp,"tmp.sms.all_files_unshuffled1.fastq"), join(self.outpath, f"{self.output_filename_prefix}_R1.fastq"), join(self.temp,"tmp.sms.random_data"))
        shuffle_fastq_file(join(self.temp,"tmp.sms.all_files_unshuffled2.fastq"), join(self.outpath, f"{self.output_filename_prefix}_R2.fastq"), join(self.temp,"tmp.sms.random_data"))


def shuffle_fastq_file(input_filename, output_filename, random_seed):
    logging.info(f"Shuffling {output_filename}")
    # additionally, this changes all '&' characters back to '/' characters. 
    os.system(f"paste -s -d '\t\t\t\n' {input_filename} | shuf --random-source={random_seed} | tr '\t&' '\n/' > {output_filename}")

@contextmanager
def art_illumina(outpath, output_filename_prefix, read_length, seq_sys, verbose,temp, nreads):
    
    try:
        yield ArtIllumina(outpath, output_filename_prefix, read_length, seq_sys, verbose,temp, nreads)
    
    finally:
        logging.info("Exiting sars-cov-2 metagenome simulator - tidying up.")

        for tem in glob.glob(join(temp,"tmp.sms.*")):
            os.remove(tem)

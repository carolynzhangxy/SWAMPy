import argparse
from os.path import dirname, join, abspath, basename
import os
import glob
import logging
from Bio import SeqIO
import subprocess
import pandas as pd
import numpy as np

from art_runner import art_illumina
from create_amplicons import build_index, align_primers, write_amplicon
from read_model import get_amplicon_reads_sampler
from PCR_error import add_PCR_errors


# All these caps variables are set once (by user inputs, with default values) but then never touched again.
BASE_DIR = join(dirname(dirname(abspath(__file__))), "example")
GENOMES_FILE = join(BASE_DIR, "genomes.fasta")
GENOMES_FOLDER = join(BASE_DIR, "genomes")
AMPLICONS_FOLDER = join(BASE_DIR, "amplicons")
INDICES_FOLDER = join(BASE_DIR, "indices")
ABUNDANCES_FILE = join(BASE_DIR, "abundances.tsv")
PRIMERS_FILE = join(BASE_DIR, "artic_v3_primers_no_alts.fastq")
OUTPUT_FOLDER = os.getcwd()
OUTPUT_FILENAME_PREFIX = "example"
N_READS = 100000
READ_LENGTH = 250
SEQ_SYS = "MSv3"
SEED = np.random.randint(1000000000)
AMPLICON_DISTRIBUTION = "DIRICHLET_1"
AMPLICON_DISTRIBUTION_FILE = join(BASE_DIR, "artic_v3_amplicon_distribution.tsv")
AMPLICON_PSEUDOCOUNTS = 10000

##PCR-error related variables:
WUHAN_REF = join(BASE_DIR, "ref","MN908947.3")
PRIMER_BED = join(BASE_DIR,"articV3_no_alt.bed")
U_SUBS_RATE = 0.002485
U_INS_RATE = 0.00002
U_DEL_RATE = 0.000115
R_SUBS_RATE = 0.003357
R_INS_RATE = 0.00002
R_DEL_RATE = 0

DEL_LENGTH_GEOMETRIC_PARAMETER = 0.69
INS_MAX_LENGTH = 14

SUBS_VAF_DIRICLET_PARAMETER = "0.36,0.27"
INS_VAF_DIRICLET_PARAMETER = "0.33,0.45"
DEL_VAF_DIRICLET_PARAMETER = "0.59,0.42"

R_SUBS_VAF_DIRICLET_PARAMETER = SUBS_VAF_DIRICLET_PARAMETER
R_INS_VAF_DIRICLET_PARAMETER = INS_VAF_DIRICLET_PARAMETER
R_DEL_VAF_DIRICLET_PARAMETER = DEL_VAF_DIRICLET_PARAMETER

def setup_parser():
    parser = argparse.ArgumentParser(description="Run SARS-CoV-2 metagenome simulation.")
    parser.add_argument("--genomes_file", metavar='', help="File containing all of the genomes that might be used", default=GENOMES_FILE)
    parser.add_argument("--genomes_folder", "-g", metavar='', help="A temporary folder containing fasta files of genomes used in the simulation.", default=GENOMES_FOLDER)
    parser.add_argument("--amplicons_folder", "-am", metavar='', help="A temporary folder that will contain amplicons of all the genomes.", default=AMPLICONS_FOLDER)
    parser.add_argument("--indices_folder", "-i", metavar='', help="A temporary folder where bowtie2 indices are created and stored.", default=INDICES_FOLDER)
    parser.add_argument("--genome_abundances", "-ab", metavar='', help="TSV of genome abundances.", default=ABUNDANCES_FILE)
    parser.add_argument("--primers_file", "-p", metavar='', help="Path to fastq file of primers. Default ARTIC V3 primers.", default=PRIMERS_FILE)
    parser.add_argument("--output_folder", "-o", metavar='', help="Folder where the output fastq files will be stored,", default=OUTPUT_FOLDER)
    parser.add_argument("--output_filename_prefix", "-x", metavar='', help="Name of the fastq files name1.fastq, name2.fastq", default=OUTPUT_FILENAME_PREFIX)
    parser.add_argument("--seqSys", metavar='', help="Name of the sequencing system, options to use are given by the art_illumina help text, and are:" + 
    """GA1 - GenomeAnalyzer I (36bp,44bp), GA2 - GenomeAnalyzer II (50bp, 75bp)
           HS10 - HiSeq 1000 (100bp),          HS20 - HiSeq 2000 (100bp),      HS25 - HiSeq 2500 (125bp, 150bp)
           HSXn - HiSeqX PCR free (150bp),     HSXt - HiSeqX TruSeq (150bp),   MinS - MiniSeq TruSeq (50bp)
           MSv1 - MiSeq v1 (250bp),            MSv3 - MiSeq v3 (250bp),        NS50 - NextSeq500 v2 (75bp)""", default="MSv3")
    parser.add_argument("--n_reads", "-n", metavar='', help="Approximate number of reads in fastq file (subject to sampling stochasticity).", default=N_READS)
    parser.add_argument("--read_length", "-l", metavar='', help="Length of reads taken from the sequencing machine.", default=READ_LENGTH)
    parser.add_argument("--seed", "-s", metavar='', help="Random seed", default=SEED)
    parser.add_argument("--quiet", "-q", help="Add this flag to supress verbose output." ,action='store_true')
    parser.add_argument("--amplicon_distribution", metavar='', default=AMPLICON_DISTRIBUTION)
    parser.add_argument("--amplicon_distribution_file", metavar='', default=AMPLICON_DISTRIBUTION_FILE)
    parser.add_argument("--amplicon_pseudocounts","-c", metavar='', default=AMPLICON_PSEUDOCOUNTS)
    parser.add_argument("--autoremove", action='store_true',help="Delete temproray files after execution.")
    parser.add_argument("--no_pcr_errors", action='store_true',help="Turn off PCR errors. The output will contain only sequencing errors. Other PCR-error related options will be ignored")
    parser.add_argument("--primer_BED", metavar='', help="BED file of the primer set. Positions wrt Wuhan ref MN908947.3", default=PRIMER_BED)
    parser.add_argument("--unique_insertion_rate","-ins", metavar='', help="PCR insertion error rate. Unique to one source genome in the mixture Default is 0.00002", default=U_INS_RATE)
    parser.add_argument("--unique_deletion_rate","-del", metavar='', help="PCR deletion error rate. Unique to one source genome in the mixture Default is 0.000115", default=U_DEL_RATE)
    parser.add_argument("--unique_substitution_rate","-subs", metavar='', help="PCR substitution error rate. Unique to one source genome in the mixture Default is 0.002485", default=U_SUBS_RATE)
    parser.add_argument("--recurrent_insertion_rate","-rins", metavar='', help="PCR insertion error rate. Recurs across source genomes. Default is 0.00002", default=R_INS_RATE)
    parser.add_argument("--recurrent_deletion_rate","-rdel", metavar='', help="PCR deletion error rate. Recurs across source genomes. Default is 0", default=R_DEL_RATE)
    parser.add_argument("--recurrent_substitution_rate","-rsubs", metavar='', help="PCR substitution error rate. Recurs across source genomes. Default is 0.003357", default=R_SUBS_RATE)
    parser.add_argument("--deletion_length_p","-dl", metavar='', help="Geometric distribution parameter, p, for PCR deletion length. Default is 0.69", default=DEL_LENGTH_GEOMETRIC_PARAMETER)
    parser.add_argument("--max_insertion_length","-il", metavar='', help="Maximum PCR insertion length in bases (uniform distribution boundry). Default is 14", default=INS_MAX_LENGTH)
    parser.add_argument("--subs_VAF_alpha","-sv", metavar='', help="alpha1,alpha2 of the Dirichlet distribution for VAF of the unique PCR error. Default is 0.36,0.27", default=SUBS_VAF_DIRICLET_PARAMETER)
    parser.add_argument("--del_VAF_alpha","-dv", metavar='', help="alpha1,alpha2 of the Dirichlet distribution for VAF of the unique PCR error. Default is 0.59,0.42", default=DEL_VAF_DIRICLET_PARAMETER)
    parser.add_argument("--ins_VAF_alpha","-iv", metavar='', help="alpha1,alpha2 of the Dirichlet distribution for VAF of the unique PCR error. Default is 0.33,0.45", default=INS_VAF_DIRICLET_PARAMETER)
    parser.add_argument("--r_subs_VAF_alpha","-rsv", metavar='', help="alpha1,alpha2 of the Dirichlet distribution for VAF of the recurrent PCR error. Default is equal to unique erros", default=SUBS_VAF_DIRICLET_PARAMETER)
    parser.add_argument("--r_del_VAF_alpha","-rdv", metavar='', help="alpha1,alpha2 of the Dirichlet distribution for VAF of the recurrent PCR error. Default is equal to unique erros", default=DEL_VAF_DIRICLET_PARAMETER)
    parser.add_argument("--r_ins_VAF_alpha","-riv", metavar='', help="alpha1,alpha2 of the Dirichlet distribution for VAF of the recurrent PCR error. Default is equal to unique erros", default=INS_VAF_DIRICLET_PARAMETER)
    return parser

def load_command_line_args():
    parser = setup_parser()
    args = parser.parse_args()

    global GENOMES_FILE
    GENOMES_FILE = args.genomes_file

    global GENOMES_FOLDER
    GENOMES_FOLDER = args.genomes_folder

    global AMPLICONS_FOLDER
    AMPLICONS_FOLDER = args.amplicons_folder

    global INDICES_FOLDER
    INDICES_FOLDER = args.indices_folder

    global ABUNDANCES_FILE 
    ABUNDANCES_FILE = args.genome_abundances

    global PRIMERS_FILE
    PRIMERS_FILE = args.primers_file

    global OUTPUT_FOLDER
    OUTPUT_FOLDER = args.output_folder

    global OUTPUT_FILENAME_PREFIX
    OUTPUT_FILENAME_PREFIX = args.output_filename_prefix
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(join(OUTPUT_FOLDER, f"{OUTPUT_FILENAME_PREFIX}.log")),
            logging.StreamHandler()
        ]
    )

    global N_READS
    N_READS = int(args.n_reads)
    logging.info(f"Number of reads: {N_READS}")

    global READ_LENGTH
    READ_LENGTH = int(args.read_length)

    global SEED
    SEED = args.seed
    np.random.seed(int(SEED))
    logging.info(f"Random seed: {SEED}")

    global VERBOSE
    VERBOSE = not args.quiet

    global AMPLICON_DISTRIBUTION
    AMPLICON_DISTRIBUTION = args.amplicon_distribution

    global AMPLICON_DISTRIBUTION_FILE
    AMPLICON_DISTRIBUTION_FILE = args.amplicon_distribution_file
    
    global AMPLICON_PSEUDOCOUNTS
    AMPLICON_PSEUDOCOUNTS = int(args.amplicon_pseudocounts)
    logging.info(f"Amplicon pseudocounts/ i.e. quality parameter: {AMPLICON_PSEUDOCOUNTS}")

    global AUTOREMOVE
    AUTOREMOVE = args.autoremove

    ##PCR error arguments

    global NO_PCR_ERRORS
    NO_PCR_ERRORS = args.no_pcr_errors

    global PRIMER_BED 
    PRIMER_BED =args.primer_BED

    global U_SUBS_RATE
    U_SUBS_RATE = args.unique_substitution_rate

    global U_INS_RATE
    U_INS_RATE = args.unique_insertion_rate

    global U_DEL_RATE
    U_DEL_RATE = args.unique_deletion_rate

    global R_SUBS_RATE
    R_SUBS_RATE = args.recurrent_substitution_rate

    global R_INS_RATE
    R_INS_RATE = args.recurrent_insertion_rate

    global R_DEL_RATE
    R_DEL_RATE = args.recurrent_deletion_rate

    global DEL_LENGTH_GEOMETRIC_PARAMETER
    DEL_LENGTH_GEOMETRIC_PARAMETER = args.deletion_length_p

    global INS_MAX_LENGTH
    INS_MAX_LENGTH = args.max_insertion_length

    global SUBS_VAF_DIRICLET_PARAMETER
    SUBS_VAF_DIRICLET_PARAMETER = args.subs_VAF_alpha.split(",")
    SUBS_VAF_DIRICLET_PARAMETER=[float(a) for a in SUBS_VAF_DIRICLET_PARAMETER]
    
    global INS_VAF_DIRICLET_PARAMETER
    INS_VAF_DIRICLET_PARAMETER = args.ins_VAF_alpha.split(",")
    INS_VAF_DIRICLET_PARAMETER=[float(a) for a in INS_VAF_DIRICLET_PARAMETER]

    global DEL_VAF_DIRICLET_PARAMETER
    DEL_VAF_DIRICLET_PARAMETER = args.del_VAF_alpha.split(",")
    DEL_VAF_DIRICLET_PARAMETER=[float(a) for a in DEL_VAF_DIRICLET_PARAMETER]

    global R_SUBS_VAF_DIRICLET_PARAMETER
    R_SUBS_VAF_DIRICLET_PARAMETER = args.r_subs_VAF_alpha.split(",")
    R_SUBS_VAF_DIRICLET_PARAMETER=[float(a) for a in R_SUBS_VAF_DIRICLET_PARAMETER]
    
    global R_INS_VAF_DIRICLET_PARAMETER
    R_INS_VAF_DIRICLET_PARAMETER = args.r_ins_VAF_alpha.split(",")
    R_INS_VAF_DIRICLET_PARAMETER=[float(a) for a in R_INS_VAF_DIRICLET_PARAMETER]

    global R_DEL_VAF_DIRICLET_PARAMETER
    R_DEL_VAF_DIRICLET_PARAMETER = args.r_del_VAF_alpha.split(",")
    R_DEL_VAF_DIRICLET_PARAMETER=[float(a) for a in R_DEL_VAF_DIRICLET_PARAMETER]


if __name__ == "__main__":

    # STEP 0: Read command line arguments
    load_command_line_args()

    # STEP 1: Simulate Viral Population

    # Read genome abundances csv file
    genome_abundances = {}
    df_amplicons = pd.DataFrame()

    with open(ABUNDANCES_FILE) as ab_file:
        for line in ab_file:
            name, relative_abundance = tuple(line.split("\t"))
            genome_abundances[name] = float(relative_abundance)

    if abs(sum(genome_abundances.values()) - 1) > 0.000000001:
        total = sum(genome_abundances.values())
        if total <= 0:
            logging.info(f"The total genome abundance is set to {total}, which is impossible.")
            exit(1)

        logging.info(f"Total of relative abundance values is {total}, not 1.")
        logging.info("Continuing, normalising total of genome abundances to 1.")

        for k in genome_abundances.keys():
            genome_abundances[k] /= total

    n_genomes = len(genome_abundances)

    # Split genome file into multiple separate files
    for genome in SeqIO.parse(GENOMES_FILE, format="fasta"):
        filepath = genome.description.replace(" ", "&").replace("/", "&")
        filepath += ".fasta"
        SeqIO.write(genome, join(GENOMES_FOLDER, filepath), format="fasta")


    # STEP 2: Simulate Amplicon Population
    genome_counter = 0
    for genome_path in genome_abundances:
        genome_counter += 1
        genome_path = genome_path.replace(" ", "&").replace("/", "&") + ".fasta"
        genome_path = join(GENOMES_FOLDER, genome_path)
        genome_filename_short = ".".join(basename(genome_path).split(".")[:-1])
        reference = SeqIO.read(genome_path, format="fasta")

        # use bowtie2 to create a dataframe with positions of each primer pair aligned to the genome
        if VERBOSE:
            logging.info(f"Working on genome {genome_counter} of {n_genomes}")
            logging.info(f"Using bowtie2 to align primers to genome {reference.description}")

        build_index(genome_path, genome_filename_short, INDICES_FOLDER)
        df = align_primers(genome_path, genome_filename_short, INDICES_FOLDER, PRIMERS_FILE, False)        
        df["abundance"] = genome_abundances[df["ref"][0]]

        # write the amplicon to a file
        write_amplicon(df, reference, genome_filename_short, AMPLICONS_FOLDER)


        df_amplicons = pd.concat([df_amplicons, df])


    # pick total numbers of reads for each amplicon
    genome_count_sampler, amplicon_hyperparameter_sampler, amplicon_probability_sampler, amplicon_reads_sampler = get_amplicon_reads_sampler(
                                AMPLICON_DISTRIBUTION, 
                                AMPLICON_DISTRIBUTION_FILE, 
                                AMPLICON_PSEUDOCOUNTS, 
                                genome_abundances,
                                N_READS)

    df_amplicons["total_n_reads"] = N_READS

    # for each amplicon, look up what the dirichlet hyperparameter should be (parameter \alpha)
    df_amplicons["hyperparameter"] = df_amplicons.apply(amplicon_hyperparameter_sampler, axis=1)

    # for each genome, sample a total number of reads that should be shared between all of its amplicons
    # N_genome = Multinomial(N_reads, p_genomes)
    df_amplicons["genome_n_reads"] = df_amplicons.apply(genome_count_sampler, axis=1)

    # sample a p_amplicon vector from the dirichlet distribution - p_amplicon = Dir(\alpha)
    df_amplicons["amplicon_prob"] = df_amplicons.apply(amplicon_probability_sampler, axis=1)

    # sample a number of reads for the amplicons of each genome: Multinomial(N_genome, p_amplicon)
    df_amplicons["n_reads"] = df_amplicons.apply(amplicon_reads_sampler, axis=1)

    # write a summary csv
    df_amplicons[
        ["ref", 
        "amplicon_number", 
        "is_alt", 
        "total_n_reads", 
        "abundance",
        "genome_n_reads",
        "hyperparameter",
        "amplicon_prob",
        "n_reads"]].to_csv(join(OUTPUT_FOLDER, f"{OUTPUT_FILENAME_PREFIX}_amplicon_abundances_summary.tsv"), sep="\t")

    df_amplicons.reset_index(drop=True,inplace=True)

    if VERBOSE:
        logging.info(f"Total number of reads was {sum(df_amplicons['n_reads'])}, when {N_READS} was expected.")


    # STEP 3: Library Prep - PCR Amplification of Amplicons

    if NO_PCR_ERRORS:    
        amplicons = [join(AMPLICONS_FOLDER, a) for a in df_amplicons["amplicon_filepath"]]
        n_reads = list(df_amplicons["n_reads"])
    else:
        if VERBOSE:
            logging.info(f"Introducing PCR errors")

        amplicons,n_reads,vcf_errordf=add_PCR_errors(df_amplicons,genome_abundances,PRIMER_BED,WUHAN_REF,AMPLICONS_FOLDER,
                                            U_SUBS_RATE,U_INS_RATE,U_DEL_RATE,R_SUBS_RATE,R_INS_RATE,R_DEL_RATE,DEL_LENGTH_GEOMETRIC_PARAMETER,INS_MAX_LENGTH,
                                            SUBS_VAF_DIRICLET_PARAMETER,INS_VAF_DIRICLET_PARAMETER,DEL_VAF_DIRICLET_PARAMETER,
                                            R_SUBS_VAF_DIRICLET_PARAMETER,R_INS_VAF_DIRICLET_PARAMETER,R_DEL_VAF_DIRICLET_PARAMETER)
       
        amplicons = [join(AMPLICONS_FOLDER, a) for a in amplicons]

        with open(f"{OUTPUT_FOLDER}/{OUTPUT_FILENAME_PREFIX}_PCR_errors.vcf","w") as o:
            o.write("##fileformat=VCFv4.3\n")
            o.write("##reference=MN908947.3\n")
            o.write('##contig=<ID=MN908947.3,length=29903>\n')
            o.write('##INFO=<ID=VAF,Number=A,Type=Float,Description="Variant Allele Frequency">\n')
            o.write('##INFO=<ID=REC,Number=A,Type=String,Description="Recurrence state across source genomes. R: recurrent; U: unique to genome">\n')
            o.write('#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n')

        vcf_errordf.to_csv(f"{OUTPUT_FOLDER}/{OUTPUT_FILENAME_PREFIX}_PCR_errors.vcf",
                            mode="a",header=False,index=False,sep="\t", float_format='%.5f')
        if VERBOSE:
            logging.info(f'All aimed PCR errros are written to "{OUTPUT_FOLDER}/{OUTPUT_FILENAME_PREFIX}_PCR_errors.vcf"')

    # STEP 4: Simulate Reads
    logging.info("Generating reads using art_illumina, cycling through all genomes and remaining amplicons.")
    with art_illumina(OUTPUT_FOLDER, OUTPUT_FILENAME_PREFIX, READ_LENGTH, SEQ_SYS,VERBOSE) as art:
        art.run(amplicons, n_reads)

    # STEP 5: Clean up all of the temp. directories
    for directory in [GENOMES_FOLDER, AMPLICONS_FOLDER, INDICES_FOLDER]:
        logging.info(f"Removing all files in {directory}")
        i = "y"

        if not AUTOREMOVE:
            logging.info(f"Press y and enter if you are ok with all files in the directory {directory}" +
            " being deleted (use flag --autoremove to stop showing this message).")
            i = input()

        if i.lower() == "y":
            files = glob.glob(join(directory, "*"))
            for f in files:
                os.remove(f)
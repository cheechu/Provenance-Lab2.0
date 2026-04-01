# These are like toolboxes we bring in to help us do our job.
# sys helps us talk to the computer about files and commands.
# json helps us turn our data into a special text format that computers can easily read.
# Bio.PDB is a special toolbox for working with protein files.
import sys
import json
from Bio.PDB import PDBParser

# This is like a recipe that tells the computer how to read a protein file.
# It takes the name of the file as input, like giving an address to find the house.
def parse_pdb(pdb_file):
    # We create a helper tool that can read protein files quietly (without extra messages).
    # It's like hiring a librarian who knows how to read protein books.
    parser = PDBParser(QUIET=True)
    
    # Now we ask the helper to read the protein file and give us the whole protein structure.
    # It's like opening a book and seeing all the pages about the protein.
    structure = parser.get_structure('protein', pdb_file)
    
    # We get the name of the protein, like reading the title on the cover.
    protein_name = structure.get_id()
    
    # We count how many chains (like separate strings) are in the protein.
    # We look at the first model (like the main version) and count its chains.
    num_chains = len(structure[0])  # Assuming the first model
    
    # We count all the building blocks (residues) in all the chains.
    # It's like counting all the letters in all the words of a story.
    num_residues = sum(len(chain) for chain in structure[0])
    
    # We try to find out how clear or detailed the protein picture is.
    # This is called resolution, like how sharp a photo is.
    # We look in the file's header (like the front page) for this info.
    resolution = None
    if 'resolution' in structure.header:
        resolution = structure.header['resolution']
    
    # We put all the information we found into a neat package.
    # It's like putting toys back in a box so they're organized.
    result = {
        'protein_name': protein_name,
        'num_chains': num_chains,
        'num_residues': num_residues,
        'resolution': resolution
    }
    
    # We give back the organized information to whoever asked for it.
    # Like returning a completed puzzle to a friend.
    return result
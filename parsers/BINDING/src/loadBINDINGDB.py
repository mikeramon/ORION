import os
import enum
import math
import zipfile as z
import requests as rq
import pandas as pd

from Common.utils import GetData
from Common.loader_interface import SourceDataLoader
from Common.extractor import Extractor

# Full Binding Data.

#make this reflect the column that the data is found in
class BD_EDGEUMAN(enum.IntEnum):
    PubChem_CID= 29
    UNIPROT_TARGET_CHAIN = 41
    ki = 9
    IC50 = 10
    kd = 11
    EC50 = 12
    kon = 13
    koff = 14

##############
# Class: Mapping Protein-Protein Interactions from STRING-DB
#
# By: Jon-Michael Beasley
# Date: 09/09/2022
# Desc: Class that loads/parses human protein-protein interaction data.


#edited for binding DB by Michael Ramon
#Desc: class that loads/parses ligand binding affinity data.
##############
class BINDINGDBLoader(SourceDataLoader):

    source_id: str = 'BINDING-DB'
    provenance_id: str = 'infores:BINDING'
    description = "A public, web-accessible database of measured binding affinities, focusing chiefly on the interactions of proteins considered to be candidate drug-targets with ligands that are small, drug-like molecules"
    source_data_url = "https://www.bindingdb.org/rwd/bind/chemsearch/marvin/SDFdownload.jsp?all_download=yes"
    license = "All data and download files in STRING are freely available under a 'Creative Commons BY 3.0' license.'"
    attribution = 'https://www.bindingdb.org/rwd/bind/info.jsp'
    parsing_version = '1.0'

    def __init__(self, test_mode: bool = False, source_data_dir: str = None):
        """
        constructor
        :param test_mode - sets the run into test mode
        """
        # call the super
        super().__init__(test_mode=test_mode, source_data_dir=source_data_dir)
#6 is the stand in threshold value until a better value can be determined
        self.ki_score_threshold = 6
        self.IC50_score_threshold = 6
        self.kd_score_threshold = 6
        self.EC50_score_threshold = 6
        self.kon_score_threshold = 6
        self.koff_score_threshold = 6

        self.ki_predicate = 'biolink:binds'
        self.IC50_predicate = 'biolink:negatively_regulates_activity_of'
        self.kd_predicate = 'biolink:binds'
        self.EC50_predicate = 'biolink:regulates_activity_of'
        self.kon_predicate = 'biolink:binds'
        self.koff_predicate = 'biolink:binds'

        self.bindingdb_version = None
        self.bindingdb_version = self.get_latest_source_version()
        self.bindingdb_data_url = [f"https://www.bindingdb.org/bind/downloads/"]

        self.BD_full_file_name = f"BindingDB_All_{self.bindingdb_version}.tsv.zip "
        self.data_files = [self.BD_full_file_name]

    def get_latest_source_version(self) -> str:
        """
        gets the latest version of the data
        :return:
        """
        if self.bindingdb_version:
            return self.bindingdb_version
        version_index = rq.get('https://www.bindingdb.org/rwd/bind/chemsearch/marvin/SDFdownload.jsp?all_download=yes').text.index('BindingDB_All_2D_') + 17
        bindingdb_version = rq.get('https://www.bindingdb.org/rwd/bind/chemsearch/marvin/SDFdownload.jsp?all_download=yes').text[version_index:version_index + 6]

        return f"{bindingdb_version}"

    def get_data(self) -> int:
        """
        Gets the yeast data.

        """
        data_puller = GetData()
        i=0
        for source in self.data_files:
            source_url = f"{self.bindingdb_data_url[i]}{source}"
            data_puller.pull_via_http(source_url, self.data_path)

            BD_full_file: str = os.path.join(self.data_path, self.BD_full_file_name)
            if ".zip" in BD_full_file:
                with z.ZipFile(BD_full_file, 'r') as fp:
                    fp.extractall(self.data_path)
            i+=1

        return True
    
    def parse_data(self) -> dict:
        """
        Parses the data file for graph nodes/edges

        :return: ret_val: load_metadata
        """
        extractor = Extractor(file_writer=self.output_file_writer)
    
        BD_full_file: str = os.path.join(self.data_path, self.BD_full_file_name)

        tsv_file = BD_full_file
        extractor.csv_extract(tsv_file,
                                lambda line: f'PUBCHEM.COMPOUND:{line[BD_EDGEUMAN.PubChem_CID.value]}',  # subject id
                                lambda line: f'UniProtKB:{line[BD_EDGEUMAN.UNIPROT_TARGET_CHAIN.value]}',  # object id
                                lambda line: self.ki_predicate if math.log(int(line[BD_EDGEUMAN.ki.value]),10) > self.ki_score_threshold else None, # predicate
                                lambda line: {"pki":-math.log(line[BD_EDGEUMAN.ki.value]*10**-9,10)},
                                comment_character=None,
                                delim="\t",
                                has_header_row=True)

        extractor.csv_extract(tsv_file,
                                lambda line: f'PUBCHEM.COMPOUND:{line[BD_EDGEUMAN.PubChem_CID.value]}',  # subject id
                                lambda line: f'UniProtKB:{line[BD_EDGEUMAN.UNIPROT_TARGET_CHAIN.value]}',  # object id
                                lambda line: self.IC50_predicate if math.log(int(line[BD_EDGEUMAN.IC50.value]),10) > self.IC50_score_threshold else None, # predicate
                                lambda line: {"pIC50":-math.log(line[BD_EDGEUMAN.IC50.value]*10**-9,10)},
                                comment_character=None,
                                delim="\t",
                                has_header_row=True)

        extractor.csv_extract(tsv_file,
                                lambda line: f'PUBCHEM.COMPOUND:{line[BD_EDGEUMAN.PubChem_CID.value]}',  # subject id
                                lambda line: f'UniProtKB:{line[BD_EDGEUMAN.UNIPROT_TARGET_CHAIN.value]}',  # object id
                                lambda line: self.kd_predicate if math.log(int(line[BD_EDGEUMAN.kd.value]),10) > self.kd_score_threshold else None, # predicate
                                lambda line: {"pkd":-math.log(line[BD_EDGEUMAN.kd.value]*10**-9,10)},
                                comment_character=None,
                                delim="\t",
                                has_header_row=True)

        extractor.csv_extract(tsv_file,
                                lambda line: f'PUBCHEM.COMPOUND:{line[BD_EDGEUMAN.PubChem_CID.value]}',  # subject id
                                lambda line: f'UniProtKB:{line[BD_EDGEUMAN.UNIPROT_TARGET_CHAIN.value]}',  # object id
                                lambda line: self.EC50_predicate if math.log(int(line[BD_EDGEUMAN.EC50.value]),10) > self.EC50_score_threshold else None, # predicate
                                lambda line: {"pEC50":-math.log(line[BD_EDGEUMAN.EC50.value]*10**-9,10)},
                                comment_character=None,
                                delim="\t",
                                has_header_row=True)
        
        extractor.csv_extract(tsv_file,
                                lambda line: f'PUBCHEM.COMPOUND:{line[BD_EDGEUMAN.PubChem_CID.value]}',  # subject id
                                lambda line: f'UniProtKB:{line[BD_EDGEUMAN.UNIPROT_TARGET_CHAIN.value]}',  # object id
                                lambda line: self.EC50_predicate if math.log(int(line[BD_EDGEUMAN.kon.value]),10) > self.kon_score_threshold else None, # predicate
                                lambda line: {"kon":line[BD_EDGEUMAN.kon.value]},
                                comment_character=None,
                                delim="\t",
                                has_header_row=True)

        extractor.csv_extract(tsv_file,
                                lambda line: f'PUBCHEM.COMPOUND:{line[BD_EDGEUMAN.PubChem_CID.value]}',  # subject id
                                lambda line: f'UniProtKB:{line[BD_EDGEUMAN.UNIPROT_TARGET_CHAIN.value]}',  # object id
                                lambda line: self.koff_predicate if float(line[BD_EDGEUMAN.kon.value])> self.koff_score_threshold else None, # predicate
                                lambda line: {"koff":line[BD_EDGEUMAN.koff.value]},
                                comment_character=None,
                                delim="\t",
                                has_header_row=True)
        return extractor.load_metadata

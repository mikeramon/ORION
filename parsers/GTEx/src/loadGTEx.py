import os
import tarfile
import gzip
import argparse
from urllib import request
from Common.utils import LoggingUtil, NodeNormUtils
from Common.kgx_file_writer import KGXFileWriter
from Common.loader_interface import SourceDataWithVariantsLoader, SourceDataBrokenError, SourceDataFailedError
from Common.node_types import SEQUENCE_VARIANT, GENE
from Common.prefixes import HGVS, UBERON
from Common.hgvs_utils import convert_variant_to_hgvs


class GTExLoader(SourceDataWithVariantsLoader):

    # this probably won't change very often - just hard code it for now
    GTEX_VERSION = "8"

    # tissue name to uberon curies, the tissue names will match gtex file names
    TISSUES = {
        "Adipose_Subcutaneous": f"{UBERON}:0002190",
        "Adipose_Visceral_Omentum": f"{UBERON}:0003688",
        "Adrenal_Gland": f"{UBERON}:0018303",
        "Artery_Aorta": f"{UBERON}:0004178",
        "Artery_Coronary": f"{UBERON}:0002111",
        "Artery_Tibial": f"{UBERON}:0007610",
        "Brain_Amygdala": f"{UBERON}:0001876",
        "Brain_Anterior_cingulate_cortex_BA24": f"{UBERON}:0006101",
        "Brain_Caudate_basal_ganglia": f"{UBERON}:0002420",
        "Brain_Cerebellar_Hemisphere": f"{UBERON}:0002245",
        "Brain_Cerebellum": f"{UBERON}:0002037",
        "Brain_Cortex": f"{UBERON}:0001851",
        "Brain_Frontal_Cortex_BA9": f"{UBERON}:0013540",
        "Brain_Hippocampus": f"{UBERON}:0002310",
        "Brain_Hypothalamus": f"{UBERON}:0001898",
        "Brain_Nucleus_accumbens_basal_ganglia": f"{UBERON}:0001882",
        "Brain_Putamen_basal_ganglia": f"{UBERON}:0001874",
        "Brain_Spinal_cord_cervical_c-1": f"{UBERON}:0002726",
        "Brain_Substantia_nigra": f"{UBERON}:0002038",
        "Breast_Mammary_Tissue": f"{UBERON}:0001911",
        "Cells_Cultured_fibroblasts": f"{UBERON}:0015764",
        "Cells_EBV-transformed_lymphocytes": f"{UBERON}:0001744",
        "Colon_Sigmoid": f"{UBERON}:0001159",
        "Colon_Transverse": f"{UBERON}:0001157",
        "Esophagus_Gastroesophageal_Junction": f"{UBERON}:0007650",
        "Esophagus_Mucosa": f"{UBERON}:0002469",
        "Esophagus_Muscularis": f"{UBERON}:0004648",
        "Heart_Atrial_Appendage": f"{UBERON}:0006618",
        "Heart_Left_Ventricle": f"{UBERON}:0002084",
        "Kidney_Cortex": f"{UBERON}:0001225",
        "Liver": f"{UBERON}:0002107",
        "Lung": f"{UBERON}:0002048",
        "Minor_Salivary_Gland": f"{UBERON}:0001830",
        "Muscle_Skeletal": f"{UBERON}:0001134",
        "Nerve_Tibial": f"{UBERON}:0001323",
        "Ovary": f"{UBERON}:0000992",
        "Pancreas": f"{UBERON}:0001264",
        "Pituitary": f"{UBERON}:0000007",
        "Prostate": f"{UBERON}:0002367",
        "Skin_Not_Sun_Exposed_Suprapubic": f"{UBERON}:0036149",
        "Skin_Sun_Exposed_Lower_leg": f"{UBERON}:0004264",
        "Small_Intestine_Terminal_Ileum": f"{UBERON}:0002116",
        "Spleen": f"{UBERON}:0002106",
        "Stomach": f"{UBERON}:0000945",
        "Testis": f"{UBERON}:0000473",
        "Thyroid": f"{UBERON}:0002046",
        "Uterus": f"{UBERON}:0000995",
        "Vagina": f"{UBERON}:0000996",
        "Whole_Blood": f"{UBERON}:0000178"}

    TEST_TISSUES = {
        "Muscle_Skeletal": f"{UBERON}:0001134",
        "Colon_Transverse": f"{UBERON}:0001157",
        "Nerve_Tibial": f"{UBERON}:0001323",
        "Brain_Cortex": f"{UBERON}:0001851",
        "Adipose_Subcutaneous": f"{UBERON}:0002190",
        "Adipose_Visceral_Omentum": f"{UBERON}:0003688",
        "Artery_Aorta": f"{UBERON}:0004178",
        "Skin_Sun_Exposed_Lower_leg": f"{UBERON}:0004264",
        "Brain_Anterior_cingulate_cortex_BA24": f"{UBERON}:0006101",
        "Cells_Cultured_fibroblasts": f"{UBERON}:0015764",
        "Adrenal_Gland": f"{UBERON}:0018303",
        "Skin_Not_Sun_Exposed_Suprapubic": f"{UBERON}:0036149"
    }

    source_id = 'GTEx'
    provenance_id = 'infores:gtex'

    def __init__(self, test_mode: bool = False, source_data_dir: str = None):
        """
        :param test_mode - sets the run into test mode
        :param source_data_dir - the specific storage directory to save files in
        """
        super().__init__(test_mode=test_mode, source_data_dir=source_data_dir)

        if self.test_mode:
            self.logger.info(f"Loading GTEx in test mode. Only expecting a subset of tissues.")
            self.anatomy_id_lookup = GTExLoader.TEST_TISSUES
        else:
            self.anatomy_id_lookup = GTExLoader.TISSUES

        # the file writer prevents duplicates by default but we can probably do it more efficiently,
        # specifically, we prevent converting the gtex variant field to hgvs multiple times,
        # and we prevent looking up potential duplicate genes from the entire list of variants
        self.gtex_variant_to_hgvs_lookup = {}
        self.variants_that_failed_hgvs_conversion = set()
        self.written_genes = set()

        # the defaults for the types/category field
        self.variant_node_types = [SEQUENCE_VARIANT]
        self.gene_node_types = [GENE]

        # accumulate edges while parsing for merging
        self.edge_list: list = []

    def get_latest_source_version(self):
        return self.GTEX_VERSION

    # the main function to call to retrieve the GTEx data and convert it to a KGX json file
    def load(self, nodes_output_file_path: str, edges_output_file_path: str):

        self.normalize_anatomy_ids()

        workspace_directory = self.data_path

        # define the urls for the raw data archives and the location to download them to
        gtex_version = self.GTEX_VERSION
        eqtl_tar_file_name = f'GTEx_Analysis_v{gtex_version}_eQTL.tar'
        eqtl_url = f'https://storage.googleapis.com/gtex_analysis_v{gtex_version}/single_tissue_qtl_data/{eqtl_tar_file_name}'
        eqtl_tar_download_path = f'{workspace_directory}{eqtl_tar_file_name}'

        sqtl_tar_file_name = f'GTEx_Analysis_v{gtex_version}_sQTL.tar'
        sqtl_url = f'https://storage.googleapis.com/gtex_analysis_v{gtex_version}/single_tissue_qtl_data/{sqtl_tar_file_name}'
        sqtl_tar_download_path = f'{workspace_directory}{sqtl_tar_file_name}'

        try:
            self.logger.debug(f'Downloading raw GTEx data files from {eqtl_url}.')

            if not self.test_mode:
                self.fetch_and_save_tar(eqtl_url, eqtl_tar_download_path)

            self.logger.debug(f'Downloading raw GTEx data files from {sqtl_url}.')

            if not self.test_mode:
                self.fetch_and_save_tar(sqtl_url, sqtl_tar_download_path)

            with KGXFileWriter(nodes_output_file_path=nodes_output_file_path,
                               edges_output_file_path=edges_output_file_path) as kgx_file_writer:

                self.logger.debug('Parsing eqtl data and writing nodes...')
                for gtex_relationship in self.parse_file_and_yield_relationships(eqtl_tar_download_path):
                    # unpack the gtex_relationship tuple
                    anatomy_id, gtex_variant, gtex_gene, p_value, slope = gtex_relationship
                    # process and write the nodes
                    variant_id = self.process_variant(gtex_variant, kgx_file_writer)
                    if variant_id:
                        gene_id = self.process_gene(gtex_gene, kgx_file_writer)
                        # create the edge (stored in self.edge_list)
                        self.create_edge(anatomy_id, variant_id, gene_id, p_value, slope)

                self.logger.debug('Merging eqtl edges and writing them...')
                self.logger.debug('Merging and writing edges...')
                # coalesce the edges that share subject/predicate/object, turning relevant properties into arrays
                # write them to file
                self.coalesce_and_write_edges(kgx_file_writer)
                self.edge_list.clear()

                self.logger.debug('Parsing sqtl data and writing nodes...')
                for gtex_relationship in self.parse_file_and_yield_relationships(sqtl_tar_download_path,
                                                                                 is_sqtl=True):
                    # unpack the gtex_relationship tuple
                    anatomy_id, gtex_variant, gtex_gene, p_value, slope = gtex_relationship
                    # process and write the nodes
                    variant_id = self.process_variant(gtex_variant, kgx_file_writer)
                    if variant_id:
                        gene_id = self.process_gene(gtex_gene, kgx_file_writer)
                        # create the edge (stored in self.edge_list)
                        self.create_edge(anatomy_id, variant_id, gene_id, p_value, slope, is_sqtl=True)

                self.logger.debug('Merging sqtl edges and writing them...')
                # coalesce the edges that share subject/predicate/object, turning relevant properties into arrays
                # write them to file
                self.coalesce_and_write_edges(kgx_file_writer)
                self.edge_list.clear()

            self.logger.debug(f'GTEx parsing and KGX file creation complete.')

        except Exception as e:
            # might be helpful to see stack trace
            # raise e
            self.logger.error(f'Exception caught. Exception: {e}')
            raise SourceDataFailedError(e)

        finally:
            # remove all the intermediate (tar) files
            if os.path.isfile(eqtl_tar_download_path):
                os.remove(eqtl_tar_download_path)
            if os.path.isfile(sqtl_tar_download_path):
                os.remove(sqtl_tar_download_path)

    # given a gtex variant check to see if it has been encountered already
    # if so return the previously generated hgvs curie
    # otherwise generate a HGVS curie from the gtex variant and write the node to file
    def process_variant(self,
                        gtex_variant_id,
                        kgx_file_writer: KGXFileWriter):
        # we might have gotten the variant from another file already
        if gtex_variant_id not in self.gtex_variant_to_hgvs_lookup:
            # if not convert it to an HGVS value
            # for gtex variant ids the format is: chr1_1413898_T_C_b38
            # split the string into it's components (3: removes "chr" from the start)
            variant_data = gtex_variant_id[3:].split('_')
            chromosome = variant_data[0]
            position = int(variant_data[1])
            ref_allele = variant_data[2]
            alt_allele = variant_data[3]
            reference_genome = variant_data[4]
            reference_patch = 'p1'
            hgvs: str = convert_variant_to_hgvs(chromosome,
                                                position,
                                                ref_allele,
                                                alt_allele,
                                                reference_genome,
                                                reference_patch)
            if hgvs:
                # store the hgvs value and write the node to the kgx file
                variant_id = f'{HGVS}:{hgvs}'
                self.gtex_variant_to_hgvs_lookup[gtex_variant_id] = variant_id
                kgx_file_writer.write_node(variant_id,
                                           node_name=hgvs,
                                           node_types=self.variant_node_types,
                                           uniquify=False)
            else:
                variant_id = None
                self.variants_that_failed_hgvs_conversion.add(gtex_variant_id)
            self.gtex_variant_to_hgvs_lookup[gtex_variant_id] = variant_id

        else:
            # if so just grab the variant id generated previously
            variant_id = self.gtex_variant_to_hgvs_lookup[gtex_variant_id]

        return variant_id

    # given a gene id from the gtex data (already converted to curie form)
    # write it to file if it hasn't been done already
    def process_gene(self,
                     gtex_gene_id,
                     kgx_file_writer: KGXFileWriter):
        # write the gene to file if needed
        if gtex_gene_id not in self.written_genes:
            # write the node to the kgx file
            kgx_file_writer.write_node(gtex_gene_id,
                                       node_name=gtex_gene_id.split(':')[1],
                                       node_types=self.gene_node_types,
                                       uniquify=False)
            self.written_genes.add(gtex_gene_id)
        return gtex_gene_id

    def create_edge(self,
                    anatomy_id: str,
                    variant_id: str,
                    gene_id: str,
                    p_value: str,
                    slope: str,
                    is_sqtl: bool = False):
        if is_sqtl:
            predicate = "CTD:affects_splicing_of"
        elif float(slope) > 0:
            predicate = "CTD:increases_expression_of"
        else:
            predicate = "CTD:decreases_expression_of"
        self.edge_list.append(
            {"subject": variant_id,
             "object": gene_id,
             "predicate": predicate,
             "expressed_in": anatomy_id,
             "p_value": float(p_value),
             "slope": float(slope)})

    def parse_file_and_yield_relationships(self,
                                           full_tar_path: str,
                                           is_sqtl: bool = False):
        # column indexes for the gtex data files
        variant_column_index = 0
        gene_column_index = 1
        pval_column_index = 6
        slope_column_index = 7

        # read the gtex tar
        with tarfile.open(full_tar_path, 'r:') as tar_files:
            # each tissue has it's own file, iterate through them
            for tissue_file in tar_files:
                # get a handle for an extracted tissue file
                tissue_handle = tar_files.extractfile(tissue_file)

                # is this a significant_variant-gene data file? expecting formats:
                # eqtl - 'GTEx_Analysis_v8_eQTL/<tissue_name>.v8.signif_variant_gene_pairs.txt.gz'
                # sqtl - 'GTEx_Analysis_v8_sQTL/<tissue_name>.v8.sqtl_signifpairs.txt.gz'
                if tissue_file.name.find('signif') != -1:
                    self.logger.debug(f'Reading tissue file {tissue_file.name}.')

                    # get the tissue name from the name of the file
                    tissue_name = tissue_file.name.split('/')[1].split('.')[0]

                    # check to make sure we know about this tissue
                    if tissue_name in self.anatomy_id_lookup:

                        # determine anatomy ID
                        anatomy_id = self.anatomy_id_lookup[tissue_name]

                        # open up the compressed file
                        with gzip.open(tissue_handle, 'rt') as compressed_file:
                            # skip the headers line of the file
                            next(compressed_file).split('\t')

                            # for each line in the file
                            for i, line in enumerate(compressed_file, start=1):

                                # split line the into an array
                                line_split: list = line.split('\t')

                                # check the column count
                                if len(line_split) != 12:
                                    self.logger.error(f'Error with column count or delimiter in {tissue_file.name}. (line {i}:{line})')
                                else:
                                    try:
                                        # get the variant gtex id
                                        gtex_variant_id: str = line_split[variant_column_index]

                                        if is_sqtl:
                                            # for sqtl the phenotype id contains the ensembl id for the gene.
                                            # it has the format: chr1:497299:498399:clu_51878:ENSG00000237094.11
                                            phenotype_id: str = line_split[gene_column_index]
                                            gene: str = phenotype_id.split(':')[4]
                                            # remove the version number
                                            gene_id: str = gene.split('.')[0]
                                        else:
                                            # for eqtl this should just be the ensembl gene id, remove the version number
                                            gene_id: str = line_split[gene_column_index].split('.')[0]

                                        gene_id = f'ENSEMBL:{gene_id}'
                                        p_value = line_split[pval_column_index]
                                        slope = line_split[slope_column_index]

                                        yield (anatomy_id,
                                               gtex_variant_id,
                                               gene_id,
                                               p_value,
                                               slope)
                                    except KeyError as e:
                                        self.logger.error(f'KeyError parsing an edge line: {e} ')
                                        continue

                    else:
                        self.logger.debug(f'Skipping unexpected tissue file {tissue_file.name}.')

    def coalesce_and_write_edges(self, kgx_file_writer: KGXFileWriter):
        """
            Coalesces edge data so that expressed_in, p_value, slope are arrays on a single edge

        :param kgx_file_writer: an already opened kgx_file_writer
        :return: Nothing
        """
        # sort the list of dicts
        self.edge_list = sorted(self.edge_list, key=lambda i: (i['subject'], i['object'], i['predicate']))

        # create a list for the anatomy_ids, p-values and slope
        anatomy_ids: list = []
        p_values: list = []
        slopes: list = []

        # prime the boundary keys
        item: dict = self.edge_list[0]

        # create boundary group keys. the key will be the subject - edge label - object
        start_group_key: str = item["subject"] + item["predicate"] + item["object"]

        # prime the loop with the first record
        cur_record: dict = item

        # loop through the edge data
        for item in self.edge_list:
            # get the current group key
            cur_group_key: str = item["subject"] + item["predicate"] + item["object"]

            # did we encounter a new grouping
            if cur_group_key != start_group_key:

                # merge the properties of the previous edge group into arrays
                edge_properties = {'expressed_in': anatomy_ids,
                                   'p_value': p_values,
                                   'slope': slopes}

                # write out the coalesced edge for the previous group
                kgx_file_writer.write_edge(subject_id=cur_record["subject"],
                                           object_id=cur_record["object"],
                                           predicate=cur_record["predicate"],
                                           original_knowledge_source=self.provenance_id,
                                           edge_properties=edge_properties)

                # reset the record storage and intermediate items for the next group
                cur_record = item
                anatomy_ids = []
                p_values = []
                slopes = []

                # save the new group key
                start_group_key = cur_group_key

            # save the uberon in the list
            anatomy_ids.append(item["expressed_in"])
            p_values.append(item["p_value"])
            slopes.append(item["slope"])

        # save anything that is left
        if len(anatomy_ids) > 0:
            # merge the properties of the previous edge group into arrays
            edge_properties = {'expressed_in': anatomy_ids,
                               'p_value': p_values,
                               'slope': slopes}

            # write out the coalesced edge for the previous group
            kgx_file_writer.write_edge(subject_id=cur_record["subject"],
                                       object_id=cur_record["object"],
                                       predicate=cur_record["predicate"],
                                       original_knowledge_source=self.provenance_id,
                                       edge_properties=edge_properties)

    # take the UBERON ids for the anatomy / tissues and normalize them with the normalization API
    # this step would normally happen post-parsing for nodes but the anatomy IDs are set as edge properties
    def normalize_anatomy_ids(self):
        node_normalizer = NodeNormUtils()
        anatomy_nodes = [{'id': anatomy_id} for anatomy_id in self.anatomy_id_lookup.values()]
        node_normalizer.normalize_node_data(anatomy_nodes)
        for anatomy_label, anatomy_id in self.anatomy_id_lookup.items():
            normalized_ids = node_normalizer.node_normalization_lookup[anatomy_id]
            if normalized_ids:
                real_anatomy_id = normalized_ids[0]
                self.anatomy_id_lookup[anatomy_label] = real_anatomy_id
            else:
                self.logger.error(f'Anatomy normalization failed to normalize: {anatomy_id} ({anatomy_label})')

    # download a tar file and write it locally
    @staticmethod
    def fetch_and_save_tar(url, dl_path):
        # get a http handle to the file stream
        http_handle = request.urlopen(url)

        # open the file and save it
        with open(dl_path, 'wb') as tar_file:
            # while there is data
            while True:
                # read a block of data
                data = http_handle.read(8192)

                # if nothing read
                if len(data) == 0:
                    break

                # write out the data to the output file
                tar_file.write(data)


# TODO use argparse to specify output location
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Retrieve, parse, and convert GTEx data to KGX files.")
    parser.add_argument('-t', '--test_mode', action='store_true')
    parser.add_argument('--data_dir', default='.')
    args = parser.parse_args()

    loader = GTExLoader(test_mode=args.test_mode)
    loader.load(args.data_dir, 'gtex_kgx')

# Literature Export Converter

Converts a few export files to Bibfiles. Currently supported: [PubMed RIS](https://pubmed.ncbi.nlm.nih.gov/help/#pubmed-format), [Scopus CSV](https://supportcontent.elsevier.com/Support%20Hub/DaaS/36182_Scopus_Custom_Data_Documentation_csv_txt_formats.pdf) and [IEEE CSV](https://ieeexplore.ieee.org/Xplorehelp/ieee-xplore-training/user-tips)

## Installation

You can install all requirements using poetry:

```sh
poetry install
```

## Manual installation

You can also choose to install requirements manually. You will need:

* `bibtexparser`: to write BibTex files. Requires at least version 2
* `pyyaml`: to parse the mapping files, which are YAML.

Install these two packages like this:

```sh
pip install --pre bibtexparser  # version 2 is in pre-release at the time of writing
pip install pyyaml
```

## Usage

```sh
python convert.py --help
```

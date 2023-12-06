import argparse
import csv
import functools
import itertools
import os
import sys
from typing import Dict, List, Iterable

from bibtexparser.bwriter import BibTexWriter
from bibtexparser.bibdatabase import BibDatabase
import yaml


class RISFileReader:
    """Read a RIS file entry by entry, returning a dictionary for each entry."""

    def __init__(self, path: str):
        """Initialize the reader with a path to a RIS file.

        Keyword arguments:
        path -- Path to RIS file.
        """
        self.path = path

    def __enter__(self):
        """Entering a RISFileReader opens the file under path (see __init__)."""
        self.file = open(self.path, "r")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exiting a RISFileReader closes the file under path (see __init__)."""
        self.file.close()

    def __iter__(self):
        """Initializing an iterator over a RISFileReader resets the file pointer."""
        self.file.seek(0)
        return self

    def ris_to_dict(lines: List[str]) -> Dict[str, str]:
        """Transforms a list of lines in RIS format to a dictionary. Multiple
        lines for a key are split using ';' as a delimiter.

        Keyword arguments:
        lines -- List of lines in RIS format.

        Returns:
        Dictionary with keys and values from RIS file.
        """
        content = {}
        oldkey = None  # needed for multiline entries
        for line in lines:
            key, value = line[0:4].strip(), line[6:].strip()
            if key == "":
                content[oldkey] += f" {value}"
            else:
                if key in content:
                    content[key] += f"; {value}"
                else:
                    content[key] = value
                oldkey = key
        return content

    def __next__(self):
        """Iterating over a RISFileReader returns a dictionary for each entry."""
        read_lines = []
        for line in self.file:
            if line.strip() == "":
                return RISFileReader.ris_to_dict(read_lines)
            read_lines.append(line)
        if len(read_lines) == 0:
            raise StopIteration
        return RISFileReader.ris_to_dict(read_lines)


@functools.lru_cache
def get_syntax_map(dialect: str):
    """Read a syntax mapping. The method ensures that we can cache the mapping.

    Keyword arguments:
    dialect -- The dialect for which the mapping should be read.
    """
    with open("syntax_mapping.yaml", "r") as syn_file:
        syntax_map = yaml.safe_load(syn_file)[dialect]
    return syntax_map


@functools.lru_cache
def get_semantic_map(dialect: str):
    """Read a semantic mapping. The method ensures that we can cache the
    mapping.

    Keyword arguments:
    dialect -- The dialect for which the mapping should be read.
    """
    with open("semantic_mapping.yaml", "r") as sem_file:
        semantic_map = yaml.safe_load(sem_file)[dialect]
    return semantic_map


# https://docs.python.org/3/library/itertools.html#itertools-recipes
def batched(iterable, n):
    "Batch data into tuples of length n. The last batch may be shorter."
    # batched('ABCDEFG', 3) --> ABC DEF G
    if n < 1:
        raise ValueError('n must be at least one')
    it = iter(iterable)
    while batch := tuple(itertools.islice(it, n)):
        yield batch


def schema_map(i: int, row: dict, dialect: str):
    """Map a row of data according to the syntax mapping defined with dialect.

    Keyword arguments:
    i -- The index of the row. Useful to autogenerate IDs.
    row -- The row of data to be mapped as a dictionary.
    dialect -- The dialect for which the mapping should be applied.
    """
    entry = {"ID": f"{dialect}_{i}"}
    syntax_map = get_syntax_map(dialect)
    for synmap in syntax_map:
        for key, bib_key in synmap.items():
            if key not in row or row[key] == "":
                continue
            entry[bib_key] = row[key]
    return entry


def semantic_map(entry: dict, dialect: str):
    """Map a row of data according to the semantic mapping defined with dialect.

    Keyword arguments:
    entry -- The entry of data to be mapped as a dictionary.
    dialect -- The dialect for which the mapping should be applied.
    """
    semantic_map = get_semantic_map(dialect)
    for key, value in entry.items():
        if key in semantic_map:
            entry[key] = semantic_map[key][value]
    return entry


def clean_entry(entry: dict, dialect: str):
    """Clean an entry according to the dialect. This is essentially a switch
    for individual cleaning functions.

    Keyword arguments:
    entry -- The entry of data to be cleaned as a dictionary.
    dialect -- The dialect for which the cleaning should be applied.
    """
    # clean: only one publication title
    if entry["ENTRYTYPE"] == "article":
        entry.pop("booktitle", None)
    else:
        entry.pop("journal", None)
    if dialect == "ieee":
        entry = ieee_clean_entry(entry)
    elif dialect == "scopus":
        entry = scopus_clean_entry(entry)
    elif dialect == "pubmed":
        entry = pubmed_clean_entry(entry)
    else:
        raise ValueError(f"Unknown dialect: {dialect}")
    return entry


def ieee_clean_entry(entry: dict):
    """Clean entries from IEEE Xplore CSV files: transform the authors field
    and remove superfloous titles (depending on their type).

    Keyword arguments:
    entry -- The entry of data to be cleaned as a dictionary.
    """
    # clean: canonicalize author name format
    if "author" in entry:
        entry["author"] = entry["author"].replace("; ", " and ")
    return entry


def scopus_author_canonicalize(authors: str):
    """Canonicalize author names from Scopus CSV files. The method returns None
    if the author name is "[No author name available]". Moreover, it adapts to
    incomplete names by checking for a dot in the first name.

    Keyword arguments:
    authors -- The author names as a string.
    """
    if authors == "[No author name available]":
        return None
    author_split = authors.split(",")
    names = []
    i = 0
    while i < len(author_split) - 1:
        last_name, first_name = author_split[i: i+2]
        if "." not in first_name:
            names.append(last_name.strip())
            i += 1
        else:
            names.append(f"{last_name.strip()}, {first_name.strip()}")
            i += 2
    return " and ".join(names)


def scopus_clean_entry(entry: dict):
    """Clean entries from Scopus CSV files: transform the authors field and
    remove superfloous titles (depending on their type).

    Keyword arguments:
    entry -- The entry of data to be cleaned as a dictionary.
    """
    # clean: canonicalize author name format
    if "author" in entry:
        author = scopus_author_canonicalize(entry["author"])
        if author is None:
            entry.pop("author")
        else:
            entry["author"] = author
    return entry


def pubmed_clean_entry(entry: dict):
    """Clean entries from PubMed RIS files: transform the authors field and
    clean the DOI field.
    """
    # clean: only one publication title
    if "author" in entry:
        entry["author"] = entry["author"].replace("; ", " and ")
    # clean: choose DOI from the IDs field
    if "doi" in entry:
        doi = None
        for article_id in entry["doi"].split(";"):
            if article_id.strip().endswith("[doi]"):
                doi = article_id.strip()[:-5].strip()
        if doi:
            entry["doi"] = doi
        else:
            entry.pop("doi")
    # clean: publication date
    if "year" in entry:
        entry["year"] = entry["year"][0:4]
    return entry


def pubmed_preprocess(entry: dict):
    """Preprocess the PT field from pubmed entries: remove all publication
    types except the first one.
    """
    candidate_pts = get_semantic_map("pubmed")["ENTRYTYPE"].keys()
    all_pts = entry["PT"].split("; ")
    found_pts = set(candidate_pts) & set(all_pts)
    if len(found_pts) > 0:
        entry["PT"] = list(found_pts)[0]
    else:
        entry["PT"] = "Journal Article"
    return entry


def preprocess_entry(entry: dict, dialect: str):
    if dialect in ["ieee", "scopus"]:
        return entry
    if dialect == "pubmed":
        return pubmed_preprocess(entry)


def transform(dialect: str, entries: Iterable[dict]):
    """Iteratively transform each entry according to their dialect.

    Keyword arguments:
    dialect -- The dialect for which the mapping should be applied.
    entries -- The entries to iterate over.

    Returns:
    A BibDatabase object containing the transformed entries.
    """
    database = BibDatabase()
    for i, row in enumerate(entries):
        entry = preprocess_entry(row, dialect)
        entry = schema_map(i, entry, dialect)
        entry = semantic_map(entry, dialect)
        entry = clean_entry(entry, dialect)
        database.entries.append(entry)
    return database


def convert_csv(dialect: str, csvfile: str, bibfile: str):
    """Convert a CSV file to a Bibfile.

    Keyword arguments:
    dialect -- Format of the input file.
    csvfile -- Path to CSV.
    bibfile -- Path to BibTeX file.
    """
    with open(csvfile, "r") as f:
        bom = f.read(1)
        if bom != "\ufeff":
            f.seek(0)
        reader = csv.DictReader(f, delimiter=",")
        database = transform(dialect, reader)
    writer = BibTexWriter()
    with open(bibfile, "w") as file:
        file.write(writer.write(database))


def convert_ris(dialect: str, risfile: str, bibfile: str):
    """Convert a RIS file to a Bibfile.

    Keyword arguments:
        dialect -- Format of the input file.
        risfile -- Path to RIS.
        bibfile -- Path to BibTeX file.
    """
    with RISFileReader(risfile) as ris:
        database = transform(dialect, ris)
    writer = BibTexWriter()
    with open(bibfile, "w") as file:
        file.write(writer.write(database))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert a library file to a Bibfile.")
    parser.add_argument(
        "format",
        type=str,
        help="Format of the input file.",
        choices=["ieee", "scopus", "pubmed"]
    )
    parser.add_argument("file", type=str, help="Path to the source file.")
    parser.add_argument("bibfile", type=str, help="Path to BibTeX file.")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print("Source file does not exist.")
        sys.exit(1)

    if args.format in ["ieee", "scopus"]:
        convert_csv(args.format, args.file, args.bibfile)
    if args.format in ["pubmed"]:
        convert_ris(args.format, args.file, args.bibfile)

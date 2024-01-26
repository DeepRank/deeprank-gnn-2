#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# QMCTorch documentation build configuration file, created by
# sphinx-quickstart on Wed Apr 22 17:16:01 2020.
#
# This file is execfile()d with the current directory set to its
# containing dir.
#
# Note that not all possible configuration values are present in this
# autogenerated file.
#
# All configuration values have a default; values that are commented out
# serve to show the default.

import configparser

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
import os
import sys

import toml  # pyright: ignore[reportMissingModuleSource]

autodoc_mock_imports = [
    "numpy",
    "scipy",
    "h5py",
    "sklearn",
    "scipy.signal",
    "torch",
    "torch.utils",
    "torch.utils.data",
    "matplotlib",
    "matplotlib.pyplot",
    "torch.autograd",
    "torch.nn",
    "torch.optim",
    "torch.cuda",
    "torch.distributions",
    "torch_sparse",
    "torch_scatter",
    "torch_cluster",
    "torch-spline-conv",
    "pdb2sql",
    "networkx",
    "mendeleev",
    "pandas",
    "tqdm",
    "horovod",
    "numba",
    "Bio",
    "torch_geometric",
    "community",
    "markov_clustering",
]

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("../"))


# -- General configuration ------------------------------------------------

# If your documentation needs a minimal Sphinx version, state it here.
#
# needs_sphinx = '1.0'

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.doctest",
    "sphinx.ext.intersphinx",
    "sphinx.ext.todo",
    "sphinx.ext.coverage",
    "sphinx.ext.mathjax",
    "sphinx.ext.ifconfig",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "myst_parser",
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# The suffix(es) of source filenames.
# You can specify multiple suffix as a list of string:
#
source_suffix = [".rst", ".md"]

# The master toctree document.
master_doc = "index"

# General information about the project.
project = "deeprank2"
author = "Sven van der Burg, Giulia Crocioni, Dani Bodor"
copyright = f"2022, {author}"

# The version info for the project you're documenting, acts as replacement for
# |version| and |release|, also used in various other places throughout the
# built documents.
#
# The short X.Y version.
with open("./../pyproject.toml", "r") as f:
    toml_file = toml.load(f)
    version = toml_file["project"]["version"]
# The full version, including alpha/beta/rc tags.
release = version

# The language for content autogenerated by Sphinx. Refer to documentation
# for a list of supported languages.
#
# This is also used if you do content translation via gettext catalogs.
# Usually you set "language" from the command line for these cases.
language = "en"

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This patterns also effect to html_static_path and html_extra_path
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = "sphinx"

# If true, `todo` and `todoList` produce output, else they produce nothing.
todo_include_todos = False


# -- Options for HTML output ----------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
# on_rtd = os.environ.get('READTHEDOCS') == 'True'
# if on_rtd:
#     html_theme = 'default'
# else:
#     html_theme = 'classic'

html_theme = "sphinx_rtd_theme"
# html_logo = "qmctorch_white.png"

# Theme options are theme-specific and customize the look and feel of a theme
# further.  For a list of options available for each theme, see the
# documentation.
#
# html_theme_options = {
#     "rightsidebar": 'true',
#     "relbarbgcolor": "black"
# }

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]

# Custom sidebar templates, must be a dictionary that maps document names
# to template names.
#
# This is required for the alabaster theme
# refs: http://alabaster.readthedocs.io/en/latest/installation.html#sidebars
html_sidebars = {
    "**": [
        "globaltoc.html",
        "relations.html",  # needs 'show_related': True theme option to display
        "sourcelink.html",
        "searchbox.html",
    ]
}


# -- Options for HTMLHelp output ------------------------------------------

# Output file base name for HTML help builder.
htmlhelp_basename = "deeprank2"

# Example configuration for intersphinx: refer to the Python standard library.
intersphinx_mapping = {
    "python": ("https://docs.python.org/", None),
    "numpy": ("http://docs.scipy.org/doc/numpy/", None),
    "pytorch": ("http://pytorch.org/docs/1.4.0/", None),
}

autoclass_content = "init"
autodoc_member_order = "bysource"

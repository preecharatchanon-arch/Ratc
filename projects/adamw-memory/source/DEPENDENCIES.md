# Dependencies and software provenance

The CPU analysis commands in README require Python, NumPy and Matplotlib only. `requirements-cpu.txt` pins the versions used to verify this release; `CPU_ENVIRONMENT.json` records Python. Parquet inspection additionally requires pandas and pyarrow. LaTeX source is provided in the separate editable author bundle; TeX Live/latexmk are needed to build it.

Native experiments require PyTorch, torchvision and NumPy. Stage 07 also imports pandas, pyarrow, SciPy and scikit-learn. Recorded versions: Python 3.13.15; NumPy 2.1.3; pandas 2.2.3; pyarrow 23.0.1; SciPy 1.16.3; scikit-learn 1.6.1. Stage 07 recorded PyTorch 2.11.0+cu128, CUDA 12.8, cuDNN 91900; matching recorded PyTorch 2.11.0+cu130, CUDA 13.0, cuDNN 92700; small matching recorded torchvision 0.26.0+cu130. The exact per-campaign records are preserved in `protocols/**/ENVIRONMENT.json` and `protocols/stage07/**/manifests/environment.json`. Unknown package versions are not inferred from later environments.

Notebook mounting uses the Google Colab runtime and its `google.colab` module. The optional Drive-backed checkpoint transport/tests additionally use google-api-python-client, google-auth, google-auth-httplib2 and httplib2; their exact original package versions were not retained. Those modules are unnecessary for the CPU response checks. Built-in Python modules and local project modules are not external packages. Frozen protocols retain their original source and scientific configuration; no GPU execution is performed by opening this archive.

Official software sources and license records:

| Software | Source | License information |
|---|---|---|
| PyTorch | https://github.com/pytorch/pytorch | https://github.com/pytorch/pytorch/blob/main/LICENSE (BSD-3-Clause project license plus bundled notices) |
| torchvision | https://github.com/pytorch/vision | https://github.com/pytorch/vision/blob/main/LICENSE (BSD-3-Clause) |
| NumPy | https://numpy.org | https://numpy.org/doc/stable/license.html (BSD-3-Clause) |
| Matplotlib | https://matplotlib.org | https://matplotlib.org/stable/project/license.html (Matplotlib license, based on PSF license) |
| pandas | https://pandas.pydata.org | https://github.com/pandas-dev/pandas/blob/main/LICENSE |
| SciPy | https://scipy.org | https://github.com/scipy/scipy/blob/main/LICENSE.txt |
| scikit-learn | https://scikit-learn.org | https://github.com/scikit-learn/scikit-learn/blob/main/COPYING |
| pyarrow | https://arrow.apache.org | https://github.com/apache/arrow/blob/main/LICENSE.txt |
| Google API client | https://github.com/googleapis/google-api-python-client | Repository LICENSE |
| Google auth | https://github.com/googleapis/google-auth-library-python | Repository LICENSE |
| Google auth httplib2 | https://github.com/googleapis/google-auth-library-python-httplib2 | Repository LICENSE |
| httplib2 | https://github.com/httplib2/httplib2 | Repository LICENSE |
| Colab | https://colab.research.google.com | Runtime service terms apply |

No third-party software distributions are vendored. Their original notices and terms apply when installed. No new license is asserted for the project code or for third-party assets. Dataset images are not included. CIFAR creator distribution: https://cave.cs.toronto.edu/kriz/cifar.html ; MNIST is accessed through torchvision's existing dataset interface and the cited original dataset paper. The inspected CIFAR creator page did not provide an explicit redistribution license; that remains a disclosed checklist limitation.

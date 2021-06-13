import setuptools

with open('README.md', 'r') as f:
    readme = f.read()

setuptools.setup(
    name='bibmgr',
    version='0.1.0',
    description='Reference management tools for BibTeX',
    long_description=readme,
    author='Steven Dahdah',
    url='https://github.com/sdahdah/bibmgr',
    packages=setuptools.find_packages(),
    entry_points={
        'console_scripts': ['bibmgr=bibmgr.bibmgr:main'],
    },
    install_requires=[
        'biblib @ git+ssh://git@github.com/aclements/biblib#egg=biblib',
        'pdflu @ git+ssh://git@github.com/sdahdah/pdflu#egg=pdflu',
    ],
)

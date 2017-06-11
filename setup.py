from distutils.core import setup
import os


# Utility function to read the README file.
# Used for the long_description.  It's nice, because now 1) we have a top level
# README file and 2) it's easier to type in the README file than to put a raw
# string in below ...
def read(file_name):
    return open(os.path.join(os.path.dirname(__file__), file_name)).read()

setup(
    name='spygame',
    version='0.1.0',
    packages=['spygame'],
    url='http://www.github.com/sven1977/spygame',
    license='MIT',
    author='Sven Mika',
    author_email='sven.mika@ducandu.com',
    description='2D game engine based on pygame and level-tmx files (fully openAI gym integrated)',
    long_description=read('README.md')
)

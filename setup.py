""" Installation module """
import sys

from setuptools import setup
from setuptools.command.test import test as TestCommand

class PyTest(TestCommand):
    """ PyTest integration with setuptools """
    user_options = [('pytest-args=', 'a', "Arguments to pass to py.test")]

    def initialize_options(self):
        TestCommand.initialize_options(self)
        self.pytest_args = ["streamrecord"]

    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        #import here, cause outside the eggs aren't loaded
        import pytest
        errno = pytest.main(self.pytest_args)
        sys.exit(errno)

setup(
    name='streamrecord',
    version='0.9.0',
    description='Record and split an audio stream',
    long_description="""RecordStream allows you to record audio from streaming services (like Spotify, Deezer, Youtube, etc.) and to split this stream in tracks, named and tagged with proper informations.""",
    classifiers=[
        'Development Status :: 4 - Beta',
        'Programming Language :: Python :: 3.5',
        'License :: OSI Approved :: MIT License'
        ],
    keywords='audio stream record',
    url='http://github.com/AlexisBRENON/deezer_record',
    author='Alexis BRENON',
    author_email='brenon.alexis+streamrecord@gmail.com',
    license='MIT',
    packages=['streamrecord'],
    zip_safe=False,
    install_require=[
        'python-slugify',
        'python-xlib'
    ],
    tests_require=['pytest'],
    cmdclass={'test':PyTest},
    entry_points={
        'console_scripts': ['streamrecord=streamrecord']
    }
)


from setuptools import setup, find_packages

setup(name='gc_log_visualizer',
      version='0.3',
      description='Generate multiple gnuplot graphs from java gc log data',
      author='Eric Abbott',
      author_email='eabbott@hubspot.com',
      url='https://github.com/HubSpot/gc_log_visualizer',
      packages=find_packages(),
      zip_safe=False,
      include_package_data=True,
      install_requires=[
          'python-dateutil'
      ],
      platforms=["any"]
)

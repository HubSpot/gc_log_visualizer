# Run a gc.log through gnuplot for multiple views of GC performance

The python script will use gnuplot to graph interesting characteristics
and data from the given gc log.

 * pre/post gc amounts for total heap
 * mixed gc duration, from the start of the first event until not continued in a new minor event (g1gc)
 * count of sequentials runs of mixed gc (g1gc)
 * stop-the-world pause times from GC events, other stw events ignored
 * Count of GC stop-the-world pause times grouped by time taken
 * Multi-phase concurrent mark cycle duration (g1gc)
 * Line graph of pre-gc sizes, young old and total. to-space exhaustion events added for g1gc
 * Eden size pre/post. For g1gc shows how the alg floats the target Eden size around.

## How to run
The start and end dates are optional and can be any format gnuplot understands.
The second argument will be used as the base name for the created png files.

```
  python gc_log_visualizer.py <gc log> <optional output file base name> <optional start date/time, fmt: 2015-08-12:19:36:00> <optional end date/time, fmt: 2015-08-12:19:39:00>
  python gc_log_visualizer.py gc.log
  python gc_log_visualizer.py gc.log.0.current user-app
  python gc_log_visualizer.py gc.log 3minwindow 2015-08-12:19:36:00 2015-08-12:19:39:00
```

## gc log preparation
The script has been run on ParallelGC and G1GC logs. There may
be some oddities/issues with ParallelGC as profiling it hasn't
proven overly useful.

The following gc params are required for full functionality.

```
  -XX:+PrintGCDetails -XX:+PrintGCDateStamps -XX:+PrintGCApplicationStoppedTime -XX:+PrintAdaptiveSizePolicy
```

## gnuplot
The gc.log is parsed into flat files which are then run through
gnuplot.

```
  # osx
  brew install gnuplot
  brew unlink libjpeg
  brew install libjpeg
  brew link libjpeg
```


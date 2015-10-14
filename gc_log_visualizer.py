#!python

import sys
import re
import tempfile
import os
import dateutil.parser

class LogParser:
  heapG1GCPattern = '\s*\[Eden: ([0-9.]+)([BKMG])\(([0-9.]+)([BKMG])\)->[0-9.BKMG()]+ Survivors: ([0-9.]+)([BKMG])->([0-9.]+)([BKMG]) Heap: ([0-9.]+)([BKMG])\([0-9.BKMG]+\)->([0-9.]+)([BKMG])\([0-9.BKMG]+\)'
  parallelPattern = '\s*\[PSYoungGen: ([0-9.]+)([BKMG])->([0-9.]+)([BKMG])\([0-9.MKBG]+\)\] ([0-9.]+)([MKBG])->([0-9.]+)([MKBG])\([0-9.MKBG]+\),'
  parallelFullPattern = '\s*\[PSYoungGen: ([0-9.]+)([BKMG])->([0-9.]+)([BKMG])\([0-9.MKBG]+\)\] \[ParOldGen: [0-9.BKMG]+->[0-9.BKMG]+\([0-9.MKBG]+\)\] ([0-9.]+)([MKBG])->([0-9.]+)([MKBG])\([0-9.MKBG]+\),'
  rootScanStartPattern = '[0-9T\-\:\.\+]* ([0-9.]*): \[GC concurrent-root-region-scan-start\]'
  rootScanMarkEndPattern = '[0-9T\-\:\.\+]* ([0-9.]*): \[GC concurrent-mark-end, .*'
  rootScanEndPattern = '[0-9T\-\:\.\+]* ([0-9.]*): \[GC concurrent-cleanup-end, .*'
  mixedStartPattern = '\s*([0-9.]*): \[G1Ergonomics \(Mixed GCs\) start mixed GCs, .*'
  mixedContinuePattern = '\s*([0-9.]*): \[G1Ergonomics \(Mixed GCs\) continue mixed GCs, .*'
  mixedEndPattern = '\s*([0-9.]*): \[G1Ergonomics \(Mixed GCs\) do not continue mixed GCs, .*'
  exhaustionPattern = '.*\(to-space exhausted\).*'
  humongousObjectPattern = '.*request concurrent cycle initiation, .*, allocation request: ([0-9]*) .*, source: concurrent humongous allocation]'

  def __init__(self, input_file):
    self.timestamp = None
    self.input_file = input_file
    self.pause_file = open('pause.dat', "w+b")
    self.pause_count_file = open('pause_count.dat', "w+b")
    self.full_gc_file = open('full_gc.dat', "w+b")
    self.gc_file = open('gc.dat', "w+b")
    self.young_file = open('young.dat', "w+b")
    self.root_scan_file = open('rootscan.dat', "w+b")
    self.mixed_duration_file = open('mixed_duration.dat', "w+b")
    self.exhaustion_file = open('exhaustion.dat', "w+b")
    self.humongous_objects_file = open('humongous_objects.dat', "w+b")
    self.gc_alg_g1gc = False
    self.gc_alg_parallel = False
    self.pre_gc_total = 0
    self.post_gc_total = 0
    self.pre_gc_young = 0
    self.pre_gc_young_target = 0
    self.pre_gc_survivor = 0
    self.post_gc_survivor = 0
    self.tenured_delta = 0
    self.full_gc = False
    self.gc = False
    self.root_scan_start_time = 0
    self.root_scan_end_timestamp = 0
    self.root_scan_mark_end_time = 0
    self.mixed_duration_start_time = 0
    self.mixed_duration_count = 0
    self.size = '1024,768'
    self.last_minute = -1
    self.reset_pause_counts()

  def cleanup(self):
    os.unlink(self.pause_file.name)
    os.unlink(self.pause_count_file.name)
    os.unlink(self.full_gc_file.name)
    os.unlink(self.gc_file.name)
    os.unlink(self.young_file.name)
    os.unlink(self.root_scan_file.name)
    os.unlink(self.mixed_duration_file.name)
    os.unlink(self.exhaustion_file.name)
    os.unlink(self.humongous_objects_file.name)
    return

  def close_files(self):
    self.pause_file.close()
    self.pause_count_file.close()
    self.gc_file.close()
    self.full_gc_file.close()
    self.young_file.close()
    self.root_scan_file.close()
    self.mixed_duration_file.close()
    self.exhaustion_file.close()
    self.humongous_objects_file.close()

  def gnuplot(self, name, start, end):
    if start is None:
      xrange = ""
    else:
      xrange = "set xrange [ \"%s\":\"%s\" ];" % (start, end)

    gnuplot_cmd = "gnuplot -e 'set term png size %s; set yrange [0:0.2]; set output \"%s-stw.png\"; set xdata time; set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; %s plot \"%s\" using 1:2'" % (self.size, name, xrange, self.pause_file.name)
    os.system(gnuplot_cmd)

    # Note: This seems to have marginal utility as compared to the plot of wall time vs. pause time
    gnuplot_cmd = "gnuplot -e 'set term png size %s; set output \"%s-pause-count.png\"; set xdata time; " \
        "set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; " \
        "%s " \
        "plot \"%s\" using 1:2 title \"under-50\" with lines" \
        ", \"%s\" using 1:3 title \"50-90\" with lines" \
        ", \"%s\" using 1:4 title \"90-120\" with lines" \
        ", \"%s\" using 1:5 title \"120-150\" with lines" \
        ", \"%s\" using 1:6 title \"150-200\" with lines" \
        ", \"%s\" using 1:7 title \"200+\" with lines'" % (self.size, name, xrange, self.pause_count_file.name, self.pause_count_file.name, self.pause_count_file.name, self.pause_count_file.name, self.pause_count_file.name, self.pause_count_file.name)
    os.system(gnuplot_cmd)

    gnuplot_cmd = "gnuplot -e 'set term png size %s; set output \"%s-heap.png\"; set xdata time; " \
        "set ylabel \"MB\"; " \
        "set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; " \
        "%s " \
        "plot \"%s\" using 1:2 title \"pre-gc-amount\"" \
        ", \"%s\" using 1:3 title \"post-gc-amount\"'" % (self.size, name, xrange, self.gc_file.name, self.gc_file.name)
    os.system(gnuplot_cmd)

    # line graph of Eden, Tenured and the Total
    # Add to-space exhaustion events if any are found
    if self.gc_alg_g1gc and os.stat(self.exhaustion_file.name).st_size > 0:
      gnuplot_cmd = "gnuplot -e 'set term png size %s; set output \"%s-totals.png\"; set xdata time; " \
          "set ylabel \"MB\";" \
          "set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; " \
          "%s " \
          "plot \"%s\" using 1:2 title \"young\" with lines" \
          ", \"%s\" using 1:4 title \"old\" with lines" \
          ", \"%s\" using 1:2 title \"to-space-exhaustion\" pt 7 ps 3" \
          ", \"%s\" using 1:5 title \"total\" with lines'" % (self.size, name, xrange, self.young_file.name, self.young_file.name, self.exhaustion_file.name, self.young_file.name)
      os.system(gnuplot_cmd)
    else:
      gnuplot_cmd = "gnuplot -e 'set term png size %s; set output \"%s-totals.png\"; set xdata time; " \
          "set ylabel \"MB\";" \
          "set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; " \
          "%s " \
          "plot \"%s\" using 1:2 title \"young\" with lines" \
          ", \"%s\" using 1:4 title \"old\" with lines" \
          ", \"%s\" using 1:5 title \"total\" with lines'" % (self.size, name, xrange, self.young_file.name, self.young_file.name, self.young_file.name)
      os.system(gnuplot_cmd)


    gnuplot_cmd = "gnuplot -e 'set term png size %s; set output \"%s-young.png\"; set xdata time; " \
        "set ylabel \"MB\"; " \
        "set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; " \
        "%s " \
        "plot \"%s\" using 1:2 title \"current\"" \
        ", \"%s\" using 1:3 title \"max\"'" % (self.size, name, xrange, self.young_file.name, self.young_file.name)
    os.system(gnuplot_cmd)

    if self.gc_alg_g1gc:
      gnuplot_cmd = "gnuplot -e 'set term png size %s; set output \"%s-tenured-delta.png\"; set xdata time; " \
          "set ylabel \"MB\"; " \
          "set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; " \
          "%s " \
          "plot \"%s\" using 1:6 with lines title \"tenured-delta\"'" % (self.size, name, xrange, self.young_file.name)
      os.system(gnuplot_cmd)

    if self.gc_alg_g1gc:
      # root-scan times
      gnuplot_cmd = "gnuplot -e 'set term png size %s; set output \"%s-root-scan.png\"; set xdata time; set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; %s plot \"%s\" using 1:2 title \"root-scan-duration(ms)\"'" % (self.size, name, xrange, self.root_scan_file.name)
      os.system(gnuplot_cmd)

      # time from first mixed-gc to last
      gnuplot_cmd = "gnuplot -e 'set term png size %s; set output \"%s-mixed-duration.png\"; set xdata time; set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; %s plot \"%s\" using 1:2 title \"mixed-gc-duration(ms)\"'" % (self.size, name, xrange, self.mixed_duration_file.name)
      os.system(gnuplot_cmd)

      # count of mixed-gc runs before stopping mixed gcs, max is 8 by default
      gnuplot_cmd = "gnuplot -e 'set term png size %s; set output \"%s-mixed-duration-count.png\"; set xdata time; set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; %s plot \"%s\" using 1:3 title \"mixed-gc-count\"'" % (self.size, name, xrange, self.mixed_duration_file.name)
      os.system(gnuplot_cmd)

      # to-space exhaustion events
      if os.stat(self.exhaustion_file.name).st_size > 0:
        gnuplot_cmd = "gnuplot -e 'set term png size %s; set output \"%s-exhaustion.png\"; set xdata time; set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; %s plot \"%s\" using 1:2'" % (self.size, name, xrange, self.exhaustion_file.name)
        os.system(gnuplot_cmd)

      # humongous object sizes
      if os.stat(self.humongous_objects_file.name).st_size > 0:
        gnuplot_cmd = "gnuplot -e 'set term png size %s; set output \"%s-humongous.png\"; set xdata time; set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; %s plot \"%s\" using 1:2 title \"humongous-object-size(KB)\"'" % (self.size, name, xrange, self.humongous_objects_file.name)
        os.system(gnuplot_cmd)

    return

  def parse_log(self):
    with open(self.input_file) as f:
      for line in f:
        # This needs to be first
        self.line_has_timestamp(line)

        self.line_has_gc(line)
        self.collect_root_scan_times(line)
        self.collect_mixed_duration_times(line)
        self.collect_to_space_exhaustion(line)
        self.collect_humongous_objects(line)

        # This needs to be last
        if self.line_has_pause_time(line):
          self.output_data()
    
  def output_data(self):
    self.pause_file.write("%s %.6f\n" % (self.timestamp_string(), self.pause_time))
    self.young_file.write("%s %s %s %s %s %s\n" % (self.timestamp_string(), self.pre_gc_young, self.pre_gc_young_target, self.pre_gc_total - self.pre_gc_young, self.pre_gc_total, self.tenured_delta))

    # clean this up, full_gc's should probably graph
    # in the same chart as regular gc events if possible
    if self.full_gc:
      self.full_gc_file.write("%s %s %s\n" % (self.timestamp_string(), self.pre_gc_total, self.post_gc_total))
      self.full_gc = False
    elif self.gc:
      self.gc_file.write("%s %s %s\n" % (self.timestamp_string(), self.pre_gc_total, self.post_gc_total))
      self.gc = False

  def output_pause_counts(self):
    self.pause_count_file.write("%s %s %s %s %s %s %s\n" % (self.timestamp_string(), self.under_50, self.under_90, self.under_120, self.under_150, self.under_200, self.over_200))

  def line_has_pause_time(self, line):
    m = re.match("[0-9-]*T[0-9]+:([0-9]+):.* threads were stopped: ([0-9.]+) seconds", line, flags=0)
    if not m or not (self.gc or self.full_gc):
      return False

    cur_minute = int(m.group(1))
    self.pause_time = float(m.group(2))
    self.increment_pause_counts(self.pause_time)

    if cur_minute != self.last_minute:
      self.last_minute = cur_minute
      self.output_pause_counts()
      self.reset_pause_counts()

    return True

  def line_has_timestamp(self, line):
    t = line.split()
    if t and len(t) > 0:
      t = t[0]
      if t:
        t = t[:-1]
   
    if t and len(t) > 15:  # 15 is mildly arbitrary
      try:
        self.timestamp = dateutil.parser.parse(t)
      except (ValueError, AttributeError), e:
        return
    return

  def timestamp_string(self):
    return self.any_timestamp_string(self.timestamp)

  def any_timestamp_string(self, ts):
    return ts.strftime("%Y-%m-%d:%H:%M:%S")

  def collect_root_scan_times(self, line):
    m = re.match(LogParser.rootScanStartPattern, line, flags=0)
    if m:
      if self.root_scan_mark_end_time > 0:
        elapsed_time = self.root_scan_mark_end_time - self.root_scan_start_time
        self.root_scan_file.write("%s %s\n" % (self.any_timestamp_string(self.root_scan_end_timestamp), elapsed_time))
        self.root_scan_mark_end_time = 0

      self.root_scan_start_time = int(float(m.group(1)) * 1000)
      return
        

    m = re.match(LogParser.rootScanMarkEndPattern, line, flags=0)
    if m and self.root_scan_start_time > 0:
      self.root_scan_mark_end_time = int(float(m.group(1)) * 1000)
      self.root_scan_end_timestamp = self.timestamp
      return

    m = re.match(LogParser.rootScanEndPattern, line, flags=0)
    if m and self.root_scan_start_time > 0:
      self.root_scan_end_timestamp = self.timestamp
      elapsed_time = int(float(m.group(1)) * 1000) - self.root_scan_start_time
      self.root_scan_file.write("%s %s\n" % (self.any_timestamp_string(self.root_scan_end_timestamp), elapsed_time))
      self.root_scan_start_time = 0
      self.root_scan_mark_end_time = 0

  def collect_mixed_duration_times(self, line):
    m = re.match(LogParser.mixedStartPattern, line, flags=0)
    if m:
      self.mixed_duration_start_time = int(float(m.group(1)) * 1000)
      self.mixed_duration_count += 1
      return

    m = re.match(LogParser.mixedContinuePattern, line, flags=0)
    if m:
      self.mixed_duration_count += 1
      return

    m = re.match(LogParser.mixedEndPattern, line, flags=0)
    if m and self.mixed_duration_start_time > 0:
      elapsed_time = int(float(m.group(1)) * 1000) - self.mixed_duration_start_time
      self.mixed_duration_count += 1
      self.mixed_duration_file.write("%s %s %s\n" % (self.timestamp_string(), elapsed_time, self.mixed_duration_count))
      self.mixed_duration_start_time = 0
      self.mixed_duration_count = 0

  def collect_to_space_exhaustion(self, line):
    m = re.match(LogParser.exhaustionPattern, line, flags=0)
    if m and self.timestamp:
      self.exhaustion_file.write("%s %s\n" % (self.timestamp_string(), 100))

  def collect_humongous_objects(self, line):
    m = re.match(LogParser.humongousObjectPattern, line, flags=0)
    if m and self.timestamp:
      self.humongous_objects_file.write("%s %s\n" % (self.timestamp_string(), int(m.group(1)) / 1024))

  def line_has_gc(self, line):
    m = re.match(LogParser.heapG1GCPattern, line, flags=0)
    if m:
      self.store_gc_amount(m)
      self.gc = True
      self.gc_alg_g1gc = True
      return

    m = re.match(LogParser.parallelPattern, line, flags=0)
    if m:
      self.gc_alg_parallel = True
      self.store_gc_amount(m)
      self.gc = True
      return

    m = re.match(LogParser.parallelFullPattern, line, flags=0)
    if m:
      self.gc_alg_parallel = True
      self.store_gc_amount(m)
      self.full_gc = True

    return

  def store_gc_amount(self, matcher):
      i = 1
      self.pre_gc_young = self.scale(matcher.group(i), matcher.group(i+1))
      i += 2
      self.pre_gc_young_target = self.scale(matcher.group(i), matcher.group(i+1))

      if self.gc_alg_g1gc:
        i += 2
        self.pre_gc_survivor = self.scale(matcher.group(i), matcher.group(i+1))
        i += 2
        self.post_gc_survivor = self.scale(matcher.group(i), matcher.group(i+1))

      i += 2
      self.pre_gc_total = self.scale(matcher.group(i), matcher.group(i+1))
      i += 2
      self.post_gc_total = self.scale(matcher.group(i), matcher.group(i+1))

      if self.gc_alg_g1gc:
        self.tenured_delta = (self.post_gc_total - self.post_gc_survivor) - (self.pre_gc_total - self.pre_gc_young - self.pre_gc_survivor)

  def scale(self, amount, unit):
    rawValue = float(amount)
    if unit == 'B':
      return int(rawValue / (1024.0 * 1024.0))
    elif unit == 'K':
      return int(rawValue / 1024.0)
    elif unit == 'M':
      return int(rawValue)
    elif unit == 'G':
      return int(rawValue * 1024.0)
    return rawValue

  def increment_pause_counts(self, pause_time):
    if pause_time < 0.050:
      self.under_50 = self.under_50 + 1
    elif pause_time < 0.090:
      self.under_90 = self.under_90 + 1
    elif pause_time < 0.120:
      self.under_120 = self.under_120 + 1
    elif pause_time < 0.150:
      self.under_150 = self.under_150 + 1
    elif pause_time < 0.200:
      self.under_200 = self.under_200 + 1
    else:
      self.over_200 = self.over_200 + 1

  def reset_pause_counts(self):
    self.under_50 = 0
    self.under_90 = 0
    self.under_120 = 0
    self.under_150 = 0
    self.under_200 = 0
    self.over_200 = 0

def main():
    logParser = LogParser(sys.argv[1])
    try:
      logParser.parse_log()
      logParser.close_files()
      basefilename = sys.argv[2] if len(sys.argv) > 2 else 'default'
      start = None
      end = None
      if len(sys.argv) > 3:
        start = sys.argv[3]
        end = sys.argv[4]
      logParser.gnuplot(basefilename, start, end)
    finally:
      logParser.cleanup()


if __name__ == '__main__':
    main()


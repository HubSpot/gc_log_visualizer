#!python

import sys
import re
import tempfile
import os
import dateutil.parser

class StwSubTimings:
  def __init__(self):
    self.reset()

  def reset(self):
    self.ext_root_scan = 0
    self.update_rs = 0
    self.scan_rs = 0
    self.object_copy = 0
    self.termination = 0
    self.other = 0

  def unknown_time(self, total):
    if total:
      return int((total * 1000) - self.ext_root_scan - self.update_rs - self.scan_rs - self.object_copy - self.termination - self.other)
    else:
      return 0

class LogParser:
  heapG1GCPattern = '\s*\[Eden: ([0-9.]+)([BKMG])\(([0-9.]+)([BKMG])\)->[0-9.BKMG()]+ Survivors: ([0-9.]+)([BKMG])->([0-9.]+)([BKMG]) Heap: ([0-9.]+)([BKMG])\([0-9.BKMG]+\)->([0-9.]+)([BKMG])\([0-9.BKMG]+\)'
  parallelPattern = '\s*\[PSYoungGen: ([0-9.]+)([BKMG])->([0-9.]+)([BKMG])\([0-9.MKBG]+\)\] ([0-9.]+)([MKBG])->([0-9.]+)([MKBG])\([0-9.MKBG]+\),'
  parallelFullPattern = '\s*\[PSYoungGen: ([0-9.]+)([BKMG])->([0-9.]+)([BKMG])\([0-9.MKBG]+\)\] \[ParOldGen: [0-9.BKMG]+->[0-9.BKMG]+\([0-9.MKBG]+\)\] ([0-9.]+)([MKBG])->([0-9.]+)([MKBG])\([0-9.MKBG]+\),'
  heapCMSPattern = '.*\[ParNew: ([0-9.]+)([BKMG])->([0-9.]+)([BKMG])\([0-9.BKMG]+\), [.0-9]+ secs\] ([0-9.]+)([BKMG])->([0-9.]+)([BKMG])\([0-9.BKMG]+\).*'
  rootScanStartPattern = '[0-9T\-\:\.\+]* ([0-9.]*): \[GC concurrent-root-region-scan-start\]'
  rootScanMarkEndPattern = '[0-9T\-\:\.\+]* ([0-9.]*): \[GC concurrent-mark-end, .*'
  rootScanEndPattern = '[0-9T\-\:\.\+]* ([0-9.]*): \[GC concurrent-cleanup-end, .*'
  mixedStartPattern = '\s*([0-9.]*): \[G1Ergonomics \(Mixed GCs\) start mixed GCs, .*'
  mixedContinuePattern = '\s*([0-9.]*): \[G1Ergonomics \(Mixed GCs\) continue mixed GCs, .*'
  mixedEndPattern = '\s*([0-9.]*): \[G1Ergonomics \(Mixed GCs\) do not continue mixed GCs, .*'
  exhaustionPattern = '.*\(to-space exhausted\).*'
  humongousObjectPattern = '.*request concurrent cycle initiation, .*, allocation request: ([0-9]*) .*, source: concurrent humongous allocation]'
  occupancyThresholdPattern = '.*threshold: ([0-9]*) bytes .*, source: end of GC\]'
  reclaimablePattern = '.*reclaimable: ([0-9]*) bytes \(([0-9.]*) %\), threshold: ([0-9]*).00 %]'

  def __init__(self, input_file):
    self.timestamp = None
    self.input_file = input_file
    self.pause_file = open('pause.dat', "w+b")
    self.young_pause_file = open('young-pause.dat', "w+b")
    self.mixed_pause_file = open('mixed-pause.dat', "w+b")
    self.pause_count_file = open('pause_count.dat', "w+b")
    self.full_gc_file = open('full_gc.dat', "w+b")
    self.gc_file = open('gc.dat', "w+b")
    self.young_file = open('young.dat', "w+b")
    self.root_scan_file = open('rootscan.dat', "w+b")
    self.cms_mark_file = open('cms_mark.dat', "w+b")
    self.cms_rescan_file = open('cms_rescan.dat', "w+b")
    self.mixed_duration_file = open('mixed_duration.dat', "w+b")
    self.exhaustion_file = open('exhaustion.dat', "w+b")
    self.humongous_objects_file = open('humongous_objects.dat', "w+b")
    self.reclaimable_file = open('reclaimable.dat', "w+b")
    self.gc_alg_g1gc = False
    self.gc_alg_cms = False
    self.gc_alg_parallel = False
    self.pre_gc_total = 0
    self.post_gc_total = 0
    self.pre_gc_young = 0
    self.pre_gc_young_target = 0
    self.post_gc_young = 0
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
    self.total_pause_time = 0
    self.size = '1024,768'
    self.last_minute = -1
    self.reset_pause_counts()
    self.occupancy_threshold = None
    self.stw = StwSubTimings()

  def cleanup(self):
    os.unlink(self.pause_file.name)
    os.unlink(self.young_pause_file.name)
    os.unlink(self.mixed_pause_file.name)
    os.unlink(self.pause_count_file.name)
    os.unlink(self.full_gc_file.name)
    os.unlink(self.gc_file.name)
    os.unlink(self.young_file.name)
    os.unlink(self.root_scan_file.name)
    os.unlink(self.cms_mark_file.name)
    os.unlink(self.cms_rescan_file.name)
    os.unlink(self.mixed_duration_file.name)
    os.unlink(self.exhaustion_file.name)
    os.unlink(self.humongous_objects_file.name)
    os.unlink(self.reclaimable_file.name)
    return

  def close_files(self):
    self.pause_file.close()
    self.young_pause_file.close()
    self.mixed_pause_file.close()
    self.pause_count_file.close()
    self.gc_file.close()
    self.full_gc_file.close()
    self.young_file.close()
    self.root_scan_file.close()
    self.cms_mark_file.close()
    self.cms_rescan_file.close()
    self.mixed_duration_file.close()
    self.exhaustion_file.close()
    self.humongous_objects_file.close()
    self.reclaimable_file.close()

  def gnuplot(self, name, start, end):
    if start is None:
      xrange = ""
    else:
      xrange = "set xrange [ \"%s\":\"%s\" ]; " % (start, end)

    # Add a line for the occupancy threshold if found
    occupancy_threshold_arrow = ""
    if self.occupancy_threshold:
      occupancy_threshold_arrow = "set arrow 10 from graph 0,first %d to graph 1, first %d nohead; " % (self.occupancy_threshold, self.occupancy_threshold)
      occupancy_threshold_arrow += "set label \"%s\" at graph 0,first %d offset 1,1; " % ('IOF' if self.gc_alg_cms else 'IHOP', self.occupancy_threshold)

    # example of how to cap the y-range of the graph at .2
    #gnuplot_cmd = "gnuplot -e 'set term png size %s; set yrange [0:0.2]; set output \"%s-stw-200ms-cap.png\"; set xdata time; set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; %s plot \"%s\" using 1:2'" % (self.size, name, xrange, self.pause_file.name)
    #os.system(gnuplot_cmd)

    if self.gc_alg_parallel:
      gnuplot_cmd = "gnuplot -e 'set term png size %s; set output \"%s-stw.png\"; set xdata time; set ylabel \"Secs\"; set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; %s plot \"%s\" using 1:2 title \"all stw\"'" % (self.size, name, xrange, self.pause_file.name)
      os.system(gnuplot_cmd)

    # Separate young and mixed stw events
    if self.gc_alg_g1gc:
      gnuplot_cmd = "gnuplot -e 'set term png size %s; set output \"%s-stw-young.png\"; set xdata time; set ylabel \"Secs\"; set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; %s plot \"%s\" using 1:2 title \"young\"'" % (self.size, name, xrange, self.young_pause_file.name)
      os.system(gnuplot_cmd)
      gnuplot_cmd = "gnuplot -e 'set term png size %s; set output \"%s-stw-mixed.png\"; set xdata time; set ylabel \"Secs\"; set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; %s plot \"%s\" using 1:2 title \"mixed\"'" % (self.size, name, xrange, self.mixed_pause_file.name)
      os.system(gnuplot_cmd)
      gnuplot_cmd = "gnuplot -e 'set term png size %s; set output \"%s-stw-all.png\"; set xdata time; " \
          "set ylabel \"Secs\"; " \
          "set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; " \
          "%s " \
          "plot \"%s\" using 1:2 title \"young\"" \
          ", \"%s\" using 1:2 title \"mixed\"'" % (self.size, name, xrange, self.young_pause_file.name, self.mixed_pause_file.name)
      os.system(gnuplot_cmd)

    # Separate young and mixed stw events
    if self.gc_alg_cms:
      gnuplot_cmd = "gnuplot -e 'set term png size %s; set output \"%s-stw-young.png\"; set xdata time; set ylabel \"Secs\"; set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; %s plot \"%s\" using 1:2 title \"young\"'" % (self.size, name, xrange, self.pause_file.name)
      os.system(gnuplot_cmd)
      gnuplot_cmd = "gnuplot -e 'set term png size %s; set output \"%s-stw-all.png\"; set xdata time; " \
          "set ylabel \"Secs\"; " \
          "set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; " \
          "%s " \
          "plot \"%s\" using 1:2 title \"young\"" \
          ", \"%s\" using 1:2 title \"mark\"" \
          ", \"%s\" using 1:2 title \"rescan\"'" % (self.size, name, xrange, self.pause_file.name, self.cms_mark_file.name, self.cms_rescan_file.name)
      os.system(gnuplot_cmd)
      gnuplot_cmd = "gnuplot -e 'set term png size %s; set output \"%s-stw-old.png\"; set xdata time; " \
          "set ylabel \"Secs\"; " \
          "set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; " \
          "%s " \
          "plot \"%s\" using 1:2 title \"mark\"" \
          ", \"%s\" using 1:2 title \"rescan\"'" % (self.size, name, xrange, self.cms_mark_file.name, self.cms_rescan_file.name)
      os.system(gnuplot_cmd)

    # Stw sub-timings
    if self.gc_alg_g1gc:
      gnuplot_cmd = "gnuplot -e 'set term png size %s; set output \"%s-substw-ext-root-scan.png\"; set xdata time; set ylabel \"millis\"; set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; %s plot \"%s\" using 1:3 title \"ext-root-scan\"'" % (self.size, name, xrange, self.pause_file.name)
      os.system(gnuplot_cmd)
      gnuplot_cmd = "gnuplot -e 'set term png size %s; set output \"%s-substw-update-rs.png\"; set xdata time; set ylabel \"millis\"; set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; %s plot \"%s\" using 1:4 title \"update-rs\"'" % (self.size, name, xrange, self.pause_file.name)
      os.system(gnuplot_cmd)
      gnuplot_cmd = "gnuplot -e 'set term png size %s; set output \"%s-substw-scan-rs.png\"; set xdata time; set ylabel \"millis\"; set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; %s plot \"%s\" using 1:5 title \"scan-rs\"'" % (self.size, name, xrange, self.pause_file.name)
      os.system(gnuplot_cmd)
      gnuplot_cmd = "gnuplot -e 'set term png size %s; set output \"%s-substw-object-copy.png\"; set xdata time; set ylabel \"millis\"; set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; %s plot \"%s\" using 1:6 title \"object-copy\"'" % (self.size, name, xrange, self.pause_file.name)
      os.system(gnuplot_cmd)
      gnuplot_cmd = "gnuplot -e 'set term png size %s; set output \"%s-substw-termination.png\"; set xdata time; set ylabel \"millis\"; set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; %s plot \"%s\" using 1:7 title \"termination\"'" % (self.size, name, xrange, self.pause_file.name)
      os.system(gnuplot_cmd)
      gnuplot_cmd = "gnuplot -e 'set term png size %s; set output \"%s-substw-other.png\"; set xdata time; set ylabel \"millis\"; set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; %s plot \"%s\" using 1:8 title \"other\"'" % (self.size, name, xrange, self.pause_file.name)
      os.system(gnuplot_cmd)
      gnuplot_cmd = "gnuplot -e 'set term png size %s; set output \"%s-substw-unknown.png\"; set xdata time; set ylabel \"millis\"; set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; %s plot \"%s\" using 1:9 title \"unknown\"'" % (self.size, name, xrange, self.pause_file.name)
      os.system(gnuplot_cmd)

    # total pause time
    gnuplot_cmd = "gnuplot -e 'set term png size %s; set output \"%s-total-pause.png\"; set xdata time; set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; %s plot \"%s\" using 1:8 title \"%% of time in gc\"'" % (self.size, name, xrange, self.pause_count_file.name)
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
        "%s " \
        "plot \"%s\" using 1:2 title \"pre-gc-amount\"" \
        ", \"%s\" using 1:3 title \"post-gc-amount\"'" % (self.size, name, occupancy_threshold_arrow, xrange, self.gc_file.name, self.gc_file.name)
    os.system(gnuplot_cmd)

    # Add to-space exhaustion events if any are found
    if self.gc_alg_g1gc and os.stat(self.exhaustion_file.name).st_size > 0:
      to_space_exhaustion = ", \"%s\" using 1:2 title \"to-space-exhaustion\" pt 7 ps 3" % (self.exhaustion_file.name)
    else:
      to_space_exhaustion = ""

    # line graph of Eden, Tenured and the Total
    gnuplot_cmd = "gnuplot -e 'set term png size %s; set output \"%s-totals.png\"; set xdata time; " \
        "set ylabel \"MB\"; " \
        "set timefmt \"%%Y-%%m-%%d:%%H:%%M:%%S\"; " \
        "%s " \
        "%s " \
        "plot \"%s\" using 1:2 title \"Eden\" with lines" \
        ", \"%s\" using 1:4 title \"Tenured\" with lines" \
        "%s" \
        ", \"%s\" using 1:5 title \"Total\" with lines" \
        ", \"%s\" using 1:2 title \"Reclaimable\"'" % (self.size, name, xrange, occupancy_threshold_arrow, self.young_file.name, self.young_file.name, to_space_exhaustion, self.young_file.name, self.reclaimable_file.name)
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

  def determine_gc_alg(self):
    with open(self.input_file) as f:
      for line in f:
        m = re.match('^CommandLine flags: .*', line, flags=0)
        if m:
          if re.match(".*-XX:\+UseG1GC.*", line, flags=0):
            self.gc_alg_g1gc = True
            pct = self.get_long_field(line, '-XX:InitiatingHeapOccupancyPercent', 45)
            max = self.get_long_field(line, '-XX:MaxHeapSize')
            if pct and max:
              self.occupancy_threshold = int(max * (pct / 100.0) / 1048576.0)
            return

          elif re.match(".*-XX:\+UseConcMarkSweepGC.*", line, flags=0):
            self.gc_alg_cms = True
            pct = self.get_long_field(line, '-XX:CMSInitiatingOccupancyFraction')
            max = self.get_long_field(line, '-XX:MaxHeapSize')
            if pct and max:
              self.occupancy_threshold = int(max * (pct / 100.0) / 1048576.0)
            return
          elif re.match(".*-XX:\+UseParallelGC.*", line, flags=0):
            self.gc_alg_parallel = True
            return

        m = re.match(LogParser.heapG1GCPattern, line, flags=0)
        if m:
          self.gc_alg_g1gc = True
          return

        m = re.match(LogParser.heapCMSPattern, line, flags=0)
        if m:
          self.gc_alg_cms = True
          return

        m = re.match(LogParser.parallelPattern, line, flags=0)
        if m:
          self.gc_alg_parallel = True
          return

  def get_long_field(self, line, field, def_value=0):
    m = re.match(".*%s=([0-9]+).*" % field, line, flags=0)
    if m:
      return long(m.group(1))
    else:
      return long(def_value)
  
  def parse_log(self):
    with open(self.input_file) as f:
      for line in f:
        # This needs to be first
        self.line_has_timestamp(line)

        self.line_has_gc(line)

        if self.gc_alg_g1gc:
          self.collect_root_scan_times(line)
          self.collect_mixed_duration_times(line)
          self.collect_to_space_exhaustion(line)
          self.collect_humongous_objects(line)
          self.collect_reclaimable(line)
          self.collect_stw_sub_timings(line)

          # find the occupance threshold if CommandLine log line not present
          if not self.occupancy_threshold:
            self.collect_occupancy_threshold_pattern(line)

        if self.gc_alg_cms:
          self.write_cms_data(line)

        # This needs to be last
        if self.line_has_pause_time(line):
          self.output_data()
          self.stw.reset()
    
  def output_data(self):
    if self.mixed_duration_count == 0:
      self.young_pause_file.write("%s %.6f\n" % (self.timestamp_string(), self.pause_time))
    else:
      self.mixed_pause_file.write("%s %.6f\n" % (self.timestamp_string(), self.pause_time))

    self.pause_file.write("%s %.6f %d %d %d %d %d %d %d\n" % (self.timestamp_string(), self.pause_time, self.stw.ext_root_scan, self.stw.update_rs, self.stw.scan_rs, self.stw.object_copy, self.stw.termination, self.stw.other, self.stw.unknown_time(self.pause_time)))
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
    self.pause_count_file.write("%s %s %s %s %s %s %s %s\n" % (self.timestamp_string(), self.under_50, self.under_90, self.under_120, self.under_150, self.under_200, self.over_200, self.total_pause_time * 100 / 60))

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

  def collect_occupancy_threshold_pattern(self, line):
    m = re.match(LogParser.occupancyThresholdPattern, line, flags=0)
    if m:
      self.occupancy_threshold = int(int(m.group(1)) / 1048576)

  def collect_reclaimable(self, line):
    m = re.match(LogParser.reclaimablePattern, line, flags=0)
    if m and int(float(m.group(2))) >= int(m.group(3)) and self.timestamp:
      self.reclaimable_file.write("%s %d\n" % (self.timestamp_string(), long(m.group(1)) / 1048576))

  def collect_stw_sub_timings(self, line):
    if re.match('^[ ]+\[.*', line):
      self.stw.ext_root_scan = self.parseMaxTiming('Ext Root Scanning', line, self.stw.ext_root_scan)
      self.stw.update_rs = self.parseMaxTiming('Update RS', line, self.stw.update_rs)
      self.stw.scan_rs = self.parseMaxTiming('Scan RS', line, self.stw.scan_rs)
      self.stw.object_copy = self.parseMaxTiming('Object Copy', line, self.stw.object_copy)
      self.stw.termination = self.parseMaxTiming('Termination', line, self.stw.termination)
      m = re.match('^[ ]+\[Other: ([0-9.]+).*', line)
      if m:
        self.stw.other = int(float(m.group(1)))

  def parseMaxTiming(self, term, line, current_value):
    m = re.match("^[ ]+\[%s .* Max: ([0-9]+)\.[0-9],.*" % (term), line)
    if m:
      return int(float(m.group(1)))
    else:
      return current_value

  def write_cms_data(self, line):
    # collect stw times
    # 1) initial marking step, checks from roots
    # 2016-04-30T06:11:03.626+0000: 120634.808: [CMS-concurrent-mark: 0.922/0.922 secs] [Times: user=7.25 sys=0.59, real=0.93 secs] 
    m = re.match(".*\[CMS-concurrent-mark: .*, real=([.0-9]+) secs.*", line, flags=0)
    if m:
      self.cms_mark_file.write("%s %.6f\n" % (self.timestamp_string(), float(m.group(1))))

    # 2) rescan phase
    # 2016-04-30T06:11:09.341+0000: 120640.523: [GC (CMS Final Remark) [YG occupancy: 737574 K (996800 K)]2016-04-30T06:11:09.341+0000: 120640.523: [Rescan (parallel) , 0.0728015 secs]2016-04-30T06:11:09.414+0000: 120640.596: [weak refs processing, 0.0236183 secs]2016-04-30T06:11:09.437+0000: 120640.619: [class unloading, 0.0157037 secs]2016-04-30T06:11:09.453+0000: 120640.635: [scrub symbol table, 0.0069954 secs]2016-04-30T06:11:09.460+0000: 120640.642: [scrub string table, 0.0007916 secs][1 CMS-remark: 22933820K(30349760K)] 23671395K(31346560K), 0.1314855 secs] [Times: user=0.83 sys=0.17, real=0.13 secs] 
    m = re.match(".*\[Rescan .*, real=([.0-9]+) secs.*", line, flags=0)
    if m:
      self.cms_rescan_file.write("%s %.6f\n" % (self.timestamp_string(), float(m.group(1))))
    

  def line_has_gc(self, line):
    m = re.match(LogParser.heapG1GCPattern, line, flags=0)
    if m:
      self.store_gc_amount(m)
      self.gc = True
      return

    m = re.match(LogParser.parallelPattern, line, flags=0)
    if m:
      self.store_gc_amount(m)
      self.gc = True
      return

    m = re.match(LogParser.parallelFullPattern, line, flags=0)
    if m:
      self.store_gc_amount(m)
      self.full_gc = True

    m = re.match(LogParser.heapCMSPattern, line, flags=0)
    if m:
      self.store_gc_amount(m)
      self.gc = True

    return

  def store_gc_amount(self, matcher):
      i = 1
      self.pre_gc_young = self.scale(matcher.group(i), matcher.group(i+1))

      if self.gc_alg_g1gc or self.gc_alg_parallel:
        i += 2
        self.pre_gc_young_target = self.scale(matcher.group(i), matcher.group(i+1))

      if self.gc_alg_cms:
        i += 2
        self.post_gc_young = self.scale(matcher.group(i), matcher.group(i+1))

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
    self.total_pause_time = self.total_pause_time + pause_time

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
    self.total_pause_time = 0

def main():
    logParser = LogParser(sys.argv[1])
    try:
      logParser.determine_gc_alg()
      print("gc alg: parallel=%s, g1gc=%s, cms=%s" % (logParser.gc_alg_parallel, logParser.gc_alg_g1gc, logParser.gc_alg_cms))
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


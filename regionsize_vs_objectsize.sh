#!/bin/bash

log=$1
if [ -z "${log}" ] ; then
  echo "Usage: ${0} <gc.log>"
  exit
fi

total=`grep "source: concurrent humongous allocation" ${log}  | wc -l`
fit2mb=`grep "source: concurrent humongous allocation" ${log} | sed 's/.*allocation request: \([0-9]*\) bytes.*/\1/' | awk '{if($1<1048576) print}' | wc -l`
fit4mb=`grep "source: concurrent humongous allocation" ${log} | sed 's/.*allocation request: \([0-9]*\) bytes.*/\1/' | awk '{if($1<2097152) print}' | wc -l`
fit8mb=`grep "source: concurrent humongous allocation" ${log} | sed 's/.*allocation request: \([0-9]*\) bytes.*/\1/' | awk '{if($1<4194304) print}' | wc -l`
fit16mb=`grep "source: concurrent humongous allocation" ${log} | sed 's/.*allocation request: \([0-9]*\) bytes.*/\1/' | awk '{if($1<8388608) print}' | wc -l`
fit32mb=`grep "source: concurrent humongous allocation" ${log} | sed 's/.*allocation request: \([0-9]*\) bytes.*/\1/' | awk '{if($1<16777216) print}' | wc -l`

echo "${total} humongous objects referenced in ${log}"
echo `echo ${fit2mb} ${total} | awk '{printf "%2.0f", 100 * $1 / $2}'`% would not be humongous with a 2mb g1 region size
echo `echo ${fit4mb} ${total} | awk '{printf "%2.0f", 100 * $1 / $2}'`% would not be humongous with a 4mb g1 region size
echo `echo ${fit8mb} ${total} | awk '{printf "%2.0f", 100 * $1 / $2}'`% would not be humongous with a 8mb g1 region size
echo `echo ${fit16mb} ${total} | awk '{printf "%2.0f", 100 * $1 / $2}'`% would not be humongous with a 16mb g1 region size
echo `echo ${fit32mb} ${total} | awk '{printf "%2.0f", 100 * $1 / $2}'`% would not be humongous with a 32mb g1 region size

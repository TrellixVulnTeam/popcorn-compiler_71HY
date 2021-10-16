#!/bin/bash


# Increase CPU Load and run <target_app>  until the execution time reaches a target


path_sch=~/Pop_Scheduler/popcorn-scheduler/KNL_HW_Sched.txt
path_exe=~/Pop_Scheduler/popcorn-scheduler/KNL_HW_Exec.txt

cp $path_sch .
cp $path_exe .

# Row number of each table (corresponds to the application)
line_numb=1

# Run for each APP
for item in `grep , $path_sch  | cut -f1 -d,`
do


# Force APP to run on x86 using the threshold table (THS_FPGA=9999; THS_ARM=9999)
sed -i ${line_numb}s/.*/`grep -E "\s*${item}\s*,.+," $path_sch| awk -F, -v OFS=,  '{$3="9999"; print}'`/g $path_sch
sed -i ${line_numb}s/.*/`grep -E "\s*${item}\s*,.+," $path_sch| awk -F, -v OFS=,  '{$4="9999"; print}'`/g $path_sch

# run APP and record exec time
start_time=$(date +%s.%N)
./$item
end_time=$(date +%s.%N)
exec_x86=$(echo "scale=10;$end_time - $start_time" | bc -l)

echo "THS: x86 exec =  "$exec_x86
# Update Exec Time Table
sed -i ${line_numb}s/.*/`grep -E "\s*${item}\s*,.+," KNL_HW_Exec.txt| awk -F, -v OFS=, -v v1=$exec_x86 '{$2=v1; print}'`/g KNL_HW_Exec.txt







# Force APP to run on FPGA using the threshold table (THS_FPGA=0; THS_ARM=9999)
sed -i ${line_numb}s/.*/`grep -E "\s*${item}\s*,.+," $path_sch| awk -F, -v OFS=,  '{$3="0"; print}'`/g $path_sch
sed -i ${line_numb}s/.*/`grep -E "\s*${item}\s*,.+," $path_sch| awk -F, -v OFS=,  '{$4="9999"; print}'`/g $path_sch

# run APP and record exec time
start_time=$(date +%s.%N)
./$item
end_time=$(date +%s.%N)
exec_FPGA=$(echo "scale=10;$end_time - $start_time" | bc -l)

echo "THS: FPGA exec =  "$exec_FPGA
# Update Exec Time Table
sed -i ${line_numb}s/.*/`grep -E "\s*${item}\s*,.+," KNL_HW_Exec.txt| awk -F, -v OFS=, -v v1=$exec_FPGA '{$3=v1; print}'`/g KNL_HW_Exec.txt



# Force APP to run on ARM using the threshold table (THS_FPGA=9999; THS_ARM=0)
sed -i ${line_numb}s/.*/`grep -E "\s*${item}\s*,.+," $path_sch| awk -F, -v OFS=,  '{$3="9999"; print}'`/g $path_sch
sed -i ${line_numb}s/.*/`grep -E "\s*${item}\s*,.+," $path_sch| awk -F, -v OFS=,  '{$4="0"; print}'`/g $path_sch

# run APP and record exec time
start_time=$(date +%s.%N)
./$item
end_time=$(date +%s.%N)
exec_ARM=$(echo "scale=10;$end_time - $start_time" | bc -l)

echo "THS: ARM exec =  "$exec_ARM
# Update Exec Time Table
sed -i ${line_numb}s/.*/`grep -E "\s*${item}\s*,.+," KNL_HW_Exec.txt| awk -F, -v OFS=, -v v1=$exec_ARM '{$4=v1; print}'`/g KNL_HW_Exec.txt


# Get THS_FPGA
exec_time=0.00
num_runs=1

# Increase the target time by 1%
target=`echo "scale=10; $exec_FPGA*1.01" | bc`


# Run APP until exec time is greater than target 
while :
do

# CPU Load generator
for (( c=1; c<$num_runs; c++ ))
do
  ./$item >> log.txt & 
done
#  ./$item >> log.txt &


# Wait for CPU Load Generator
cpu_load=0
while [ $cpu_load -lt $num_runs ]
do
cpu_load=`ps -r | wc -l`
done

# run APP and record exec time
start_time=$(date +%s.%N)
./$item >>log2.txt 
end_time=$(date +%s.%N)
exec_time=$(echo "scale=10;$end_time - $start_time" | bc -l)

num_runs=$((num_runs+1))

echo "THS: Exec Time = $exec_time  Target = $target"

# kill the processes generated by the CPU Load generator
for pid in $(ps -a|grep './$item'|awk '{print $1}');do kill -9 $pid; done

# Wait for CPU Load Generator to finish
load_gen=0
while [ $load_gen != 0 ]
do
  load_gen=`ps -r | grep './$item' | wc -l`
done

# wait until processes are terminated
sleep 3

if (( $(echo "$target < $exec_time" | bc -l) )); then
  echo "THS: THS FPGA (Final) = $cpu_load; App = ./$item" "(`date +"%Y-%m-%d %T"`)"
  echo "*****************************"
  break
fi

echo "THS: CPU LOAD = $cpu_load"  `date +"%Y-%m-%d %T"`   
echo "*****************************"
done

# Update Threshold Table
sed -i ${line_numb}s/.*/`grep -E "\s*${item}\s*,.+," KNL_HW_Sched.txt| awk -F, -v OFS=, -v v1=$cpu_load '{$3=v1; print}'`/g KNL_HW_Sched.txt



# Get THS_ARM
exec_time=0.00
num_runs=1

# Increase the target time by 1%
target=`echo "scale=10; $exec_ARM*1.01" | bc`


# Run APP until exec time is greater than target 
while :
do

# CPU Load generator
for (( c=1; c<$num_runs; c++ ))
do
  ./$item >> log.txt & 
done
#  ./$item >> log.txt &


# Wait for CPU Load Generator
cpu_load=0
while [ $cpu_load -lt $num_runs ]
do
cpu_load=`ps -r | wc -l`
done

# run APP and record exec time
start_time=$(date +%s.%N)
./$item >>log2.txt 
end_time=$(date +%s.%N)
exec_time=$(echo "scale=10;$end_time - $start_time" | bc -l)

num_runs=$((num_runs+1))

echo "THS: Exec Time = $exec_time  Target = $target"

# kill the processes generated by the CPU Load generator
for pid in $(ps -a|grep './$item'|awk '{print $1}');do kill -9 $pid; done

# Wait for CPU Load Generator to finish
load_gen=0
while [ $load_gen != 0 ]
do
  load_gen=`ps -r | grep './$item' | wc -l`
done

# wait until processes are terminated
sleep 3

if (( $(echo "$target < $exec_time" | bc -l) )); then
  echo "THS: THS ARM (Final) = $cpu_load; App = ./$item" "(`date +"%Y-%m-%d %T"`)"
  echo "*****************************"
  break
fi

echo "THS: CPU LOAD = $cpu_load"  `date +"%Y-%m-%d %T"`   
echo "*****************************"
done

# Update Threshold Table
sed -i ${line_numb}s/.*/`grep -E "\s*${item}\s*,.+," KNL_HW_Sched.txt| awk -F, -v OFS=, -v v1=$cpu_load '{$4=v1; print}'`/g KNL_HW_Sched.txt




line_numb=$((line_numb+1))


done


# Copy the updated tables to the scheduler server folder
cp KNL_HW_Sched.txt $path_sch 
cp KNL_HW_Exec.txt $path_exe




# SICOPOLIS on HTCondor: Checkpoint-Enabled

This repository contains a Docker environment and execution tools for running the [SICOPOLIS](https://github.com/sicopolis/sicopolis) ice sheet model with checkpointing capabilities. The [Center for High Throughput Computing (CHTC)](https://chtc.cs.wisc.edu/) at the University of Wisconsin-Madison (USA) is used as the reference execution infrastructure, with [HTCondor](https://htcondor.org/) as the workload manager. However, the workflow presented here can be adapted to any system.

## SICOPOLIS Download

This repository assumes you already have a local copy of SICOPOLIS. If not, run the commands below to download the source code and required input files. For further details on the setup procedure, refer to the [official documentation](https://sicopolis.readthedocs.io/en/main/index.html).
```bash
git clone https://github.com/sicopolis/sicopolis.git
```
```bash
cd sicopolis
```
```bash
./get_input_files.sh
```
```bash
./copy_templates.sh
```

## Repository Structure
```
.
├── src/
    ├── Dockerfile                   # Dockerfile to create the sicopolis-chtc image
    ├── exec.sh                      # Main execution script with snapshot management
    ├── sico.sub                     # HTCondor submit file
    ├── sicoCheckpoints.py           # Python tool for concatenating snapshot outputs
    └── sico_specs_CheckpointTest.h  # SICOPOLIS configuration file for testing
├── LICENSE
└── README.md
```

## Docker

### Image
Contains only the runtime environment and dependencies required to run SICOPOLIS:
- Ubuntu 22.04 base
- Fortran compiler (gfortran)
- NetCDF libraries (libnetcdf-dev, netcdf-bin, libnetcdff-dev)
- LIS library (v2.1.8) for solving linear systems

**Usage**: Designed for CHTC deployments where the SICOPOLIS source code is transferred separately as `sicopolis.zip`.

### Building
```bash
cd src
```
```bash
docker build -t sicopolis-chtc:latest .
```

### Downloading from Repository
```bash
docker pull nsartore/sicopolis-chtc:latest
```

## Checkpointing with `exec.sh`

The checkpointing workflow is orchestrated by a single Bash script: `exec.sh`, which manages SICOPOLIS execution with snapshot and restart capabilities. To initiate a simulation or resume after a timeout, simply invoke the same command again.

### Command Line Usage
```bash
exec.sh <SIMULATION_NAME> <OUTPUT_NAME> <SICOPOLIS_FILE> [MAX_RUN_TIME] [CORE_NB] [ANF_PATH_INIT]
```

- `SIMULATION_NAME`: Name of the simulation configuration (must match the header file name)
- `OUTPUT_NAME`: Identifier for the output archive (typically `$(Cluster)_$(Process)`)
- `SICOPOLIS_FILE`: Name of the compressed SICOPOLIS source archive (e.g., `sicopolis.zip`)
- `MAX_RUN_TIME`: Maximum runtime before timeout (default: `1d`)
- `CORE_NB`: Number of CPU cores (default: `1`)
- `ANF_PATH_INIT`: Optional path to the initial NetCDF restart file. Used only on the first execution of `exec.sh`.

### Snapshot/Restart Mechanism

**First Run** (no existing snapshots):
1. Extracts and configures SICOPOLIS
2. Runs the simulation with an optional initial restart file (`-a` flag)
3. On timeout (exit code 85), moves output to `snapshot/00000/`

**Subsequent Runs** (snapshots exist):
1. Identifies the last completed snapshot directory: `snapshot/XXXXX/`
2. Selects the second-to-last 3D NetCDF file: `${SIMULATION_NAME}NNNN.nc`
   - The last file may be incomplete; the second-to-last provides a safe restart point
3. Extracts the time value from the NetCDF file using `ncdump`
4. Modifies the SICOPOLIS header file (`sico_specs_${SIMULATION_NAME}.h`):
   ```c
   #define TIME_INIT0 '<extracted_time>'
   #define ANFDATNAME '<snapshot_file.nc>'
   #define ANF_DAT 3
   ```
5. Runs SICOPOLIS with the updated restart configuration
6. On timeout, moves output files to an incremented `snapshot/XXXXX/` directory

## Output Concatenation with `sicoCheckpoints.py`

Each checkpoint run produces a individual snapshot directory. The Python utility `sicoCheckpoints.py` concatenates the outputs from all snapshots into a single, continuous time series.

### Dependencies
- Python 3: numpy, xarray, netCDF4
- NCO tools: ncecat, ncrcat
- Compression tools: tar, pigz

### Command Line Usage
```bash
python3 sicoCheckpoints.py <output_path>
```

### Concatenation Mechanism
1. **Cleanup**: Removes any existing concatenated files (`*1D*`, `*2D*`, `*3D*`)
2. **Iterate through snapshots**: Processes each numbered subdirectory (00000, 00001, ...)
3. **Extract time bounds**:
   - For intermediate snapshots: reads the time from the second-to-last 3D file
   - For the final snapshot: uses all available data
4. **Slice 1D data**: Extracts the time series up to the checkpoint time from `*_ser.nc`
5. **Slice 2D data**: Selects all 2D files (`*_2d_*.nc`) with time ≤ checkpoint time
6. **Concatenate**: Uses NCO tools to merge the sliced outputs
7. **Cleanup**: Removes intermediate files; retains the final `${SIMULATION_NAME}_1D.nc` and `${SIMULATION_NAME}_2D.nc`


## HTCondor Execution on CHTC

The CHTC uses HTCondor as its workload management platform. Job submission requires a configuration file: `sico.sub`.

**Container Configuration**:
```
USERNAME = <your_username>
SICOPOLIS_FILE = sicopolis.zip
MAX_RUN_TIME = <desired_maximum_runtime>
ANF_PATH_INIT = <initial_restart_file>   # optional
CORE_NB = <number_of_cpu_cores>
RAM = <maximum_ram>
DISK = <maximum_disk_space>
```

**Checkpoint/Restart Support**:
When `exec.sh` exits with code 85 (timeout), HTCondor preserves the `snapshot/` directory and automatically requeues the job, enabling long simulations to span multiple time-limited execution sessions.

**Input/Output Transfer**:
- Pulls `sicopolis.zip` from the staging area
- Returns a compressed output archive as `output_$(Cluster)_$(Process)_$(SIMULATION_NAME).tar.gz`
- Staging area path: `file:///staging/<your_username>/`

### Running Simulations on CHTC

#### 1. Prepare Input
Ensure `sicopolis.zip` is present in the staging area: `/staging/<your_username>/sicopolis.zip`

#### 2. Configure Simulation
Edit `sico.sub` to set the resource requirements and queue mode. Two queue modes are supported:

**Single simulation** (uncomment the last two lines):
```
USERNAME = bob
SICOPOLIS_FILE = sicopolis.zip
MAX_RUN_TIME = 6h
ANF_PATH_INIT = sico_in/grl
CORE_NB = 1
RAM = 1GB
DISK = 10GB

...

# SIMULATION_NAME = grl04_bm5_spinup02_holo_...  # Must match a header file
# queue 1
```

**Multiple simulations** (provide a file listing simulation names, one per line):
```
...
queue SIMULATION_NAME from simulation_list.txt
```

#### 3. Submit Job
```bash
condor_submit sico.sub
```

#### 4. Monitor Progress

##### Check job status
```bash
condor_q
```

##### Follow output log
```bash
condor_tail -f <job_id>
```

#### 5. Retrieve and Process Results
Download the output archive from the staging area:
```bash
scp <your_username>@CHTC:/staging/<your_username>/output_<cluster>_<process>_<simulation>.tar.gz output.tar.gz
```

Extract the output archive:
```bash
mkdir output
```
```bash
tar -xvf output.tar.gz -C output                    # Single-threaded decompression
```
```bash
tar -I "pigz -d -p 4" -xvf output.tar.gz -C output  # Multi-threaded decompression
```

Concatenate the time series:
```bash
python3 sicoCheckpoints.py output
```


## Docker & Checkpointing Usage Example

### Running a Simulation in Docker with `exec.sh`

The following example demonstrates how to run SICOPOLIS inside the `sicopolis-chtc` Docker image using `exec.sh` for checkpoint management. The commands use the `sico_specs_CheckpointTest.h` configuration file, running on 1 CPU core with a 9-minute timeout, which should produce approximately 3 checkpoints.

#### Using the Environment Image
After copying the sicopolis source code in the working directory and the `sico_specs_CheckpointTest.h` in the headers subdirectory, the working directory should have the following structure:
```
.
├── sicopolis_source_code/
    ├── docs/
    ├── headers/
        ├── sico_specs_CheckpointTest.h
        └── ...
    └── ...
└── exec.sh
```

```bash
docker run --user $(id -u):$(id -g) -v $(pwd):/sico -w /sico nsartore/sicopolis-chtc:latest ./exec.sh CheckpointTest prefix sicopolis.zip 9m 1
```

Depending on the computational speed of the host machine, one of two outcomes is expected:
  - A `snapshot/` directory is created if the simulation did not complete within the 9-minute timeout. In this case, re-run the same Docker command to resume the simulation.
  - A `prefix_output_CheckpointTest.tar.gz` archive is produced if the simulation completed successfully. Proceed to the next step.

### Concatenating Snapshots into a Single Output File

The snapshot directory contains numbered subdirectories (00000, 00001, 00002, etc.), one per checkpoint run. The total number of subdirectories will vary depending on the computational speed of the host machine. To concatenate all snapshots into a single output file, place `sicoCheckpoints.py` in the working directory. The expected file structure is:
```
.
├── snapshot/
    ├── 00000/
    ├── 00001/
    └── ...
├── sicopolis_source_code/
    └── ...
├── exec.sh
├── prefix_output_CheckpointTest.tar.gz
└── sicoCheckpoints.py
```

Extract the output archive and run the concatenation utility:
```bash
mkdir snapshot
```
```bash
tar -xvf prefix_output_CheckpointTest.tar.gz -C snapshot
```
```bash
python3 sicoCheckpoints.py snapshot
```

The files `CheckpointTest_1D.nc` and `CheckpointTest_2D.nc` will be generated in the `snapshot/` directory, containing the complete concatenated time series. The final directory structure should be:
```
.
├── snapshot/
    ├── 00000/
    ├── 00001/
    ├── ...
    ├── CheckpointTest_1D.nc
    └── CheckpointTest_2D.nc
├── sicopolis_source_code/
    └── ...
├── exec.sh
├── prefix_output_CheckpointTest.tar.gz
└── sicoCheckpoints.py
```

## Configuration Notes

- **Path Configuration**: `exec.sh` automatically updates `sico_configs.sh` to use the appropriate container paths:
  - `NETCDFHOME=/usr`
  - `LISHOME=/opt/lis`

- **Header Files**: The SICOPOLIS header file must exist at `headers/sico_specs_${SIMULATION_NAME}.h` within the source tree.

- **Timeout Handling**: Exit code 85 is intercepted by HTCondor as a checkpoint signal, not a job failure.

- **SICOPOLIS Header Requirements**: Proper checkpointing requires the following SICOPOLIS header parameters to be configured correctly:
  - `OUTPUT` must be set to `3`
  - `DTIME_OUT0` must evenly divide `TIME_OUT0`
  - `TIME_OUT0` must be small enough to ensure that at least 2 output files are written within a single `MAX_RUN_TIME` window

## Contact

**Nicolas B. Sartore**\
Research Assistant, [Till Wagner Group](https://tillwagner.me)\
Department of Atmospheric and Oceanic Sciences\
University of Wisconsin-Madison, USA

- Website: [nsartore.me](https://nsartore.me)
- Email: [nsartore@wisc.edu](mailto:nsartore@wisc.edu)
- GitHub: [github.com/nicsar2](https://github.com/nicsar2)

For questions or issues related to this repository, please open a GitHub issue or contact the author directly by email.

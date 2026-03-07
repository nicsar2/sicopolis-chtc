# SICOPOLIS CHTC Execution Environment

This repository contains Docker environments and execution tools for running the [SICOPOLIS](https://github.com/sicopolis/sicopolis) ice sheet model on the [Center for High Throughput Computing (CHTC)](https://chtc.cs.wisc.edu/) infrastructure with checkpoint/restart capabilities.

## Repository Structure

```
.
├── Docker/
│   ├── Environment/    # Dependencies-only Docker image
│   └── Standalone/     # Full Docker image with SICOPOLIS
└── CHTC/
    ├── exec.sh         # Main execution script with snapshot management
    ├── sicoCheckpoints # Python tool for concatenating snapshot outputs
    └── sico.sub        # HTCondor submit file
```

## Docker Images

### Docker/Environment
Contains only the runtime environment and dependencies required to run SICOPOLIS:
- Ubuntu 22.04 base
- Fortran compiler (gfortran)
- NetCDF libraries (libnetcdf-dev, netcdf-bin, libnetcdff-dev)
- LIS library (v2.1.8) for solving linear systems

**Usage**: Designed for CHTC where SICOPOLIS code is transferred separately as `sicopolis.zip` or uncompressed.

### Docker/Standalone
Includes the full SICOPOLIS environment with code automatically cloned from GitHub:
- All dependencies from Environment image
- SICOPOLIS code cloned from official repository
- Input files downloaded via `get_input_files.sh`

**Usage**: Ideal for local testing and development.

### Building Docker Images

```bash
# Build environment image (CHTC production)
cd Docker/Environment
docker build -t sicopolis-env:latest .

# Build standalone image (local testing)
cd Docker/Standalone
docker build -t sicopolis-standalone:latest .
```

### Downloading images from Repository
```bash
# CHTC version:
docker pull nsartore/sicopolis-chtc:latest

# Standalone version:
docker pull nsartore/sicopolis-standalone:latest
```

## CHTC Execution Workflow

### HTCondor Submit File (sico.sub)
Configures job submission with the following key features:

**Container Configuration**:
```
USERNAME = <your_username>
SICOPOLIS_FILE = sicopolis.zip 
MAX_RUN_TIME = <desired_maximum_runtime>
ANF_PATH_INIT = <start_simulation_file> (optional)
CORE_NB = <number_of_cpu_core>
RAM = <maximum_ram_used>
DISK = <maximum_disk_space_used>
```

**Checkpoint/Restart Support**:
When `exec.sh` exits with code 85 (timeout), HTCondor preserves the `snapshot/` directory and automatically restarts the job, enabling long simulations to run across multiple time-limited sessions.

**Input/Output Transfer**:
- Pulls `sicopolis.zip` from staging area
- Returns compressed output as `output_$(Cluster)_$(Process)_$(SIMULATION_NAME).tar.gz`
- Staging area path: `file:///staging/<your_username>/`

### Execution Script with Checkpointing (exec.sh)

The main orchestration script that manages SICOPOLIS execution with snapshot/restart capabilities. To restart code after timeout, simply run the same command again.

#### Command Line Arguments
```bash
exec.sh <SIMULATION_NAME> <OUTPUT_NAME> <SICOPOLIS_FILE> [MAX_RUN_TIME] [CORE_NB] [ANF_PATH_INIT]
```

- `SIMULATION_NAME`: Name of the simulation configuration (must match header file)
- `OUTPUT_NAME`: Identifier for output archive (typically `$(Cluster)_$(Process)`)
- `SICOPOLIS_FILE`: Name of compressed SICOPOLIS code archive (e.g., `sicopolis.zip`)
- `MAX_RUN_TIME`: Maximum runtime before timeout (default: `1d`)
- `CORE_NB`: Number of CPU cores (default: `1`)
- `ANF_PATH_INIT`: Optional path locating starting nc file. Only used at first execution of exec.sh.

#### Snapshot/Restart Mechanism

**First Run** (no existing snapshots):
1. Extracts and configures SICOPOLIS
2. Runs simulation with optional initial restart file (`-a` flag)
3. On timeout (exit code 85), moves output to `snapshot/00000/`
4. HTCondor preserves snapshot directory and restarts job

**Subsequent Runs** (snapshots exist):
1. Identifies last completed snapshot: `snapshot/XXXXX/`
2. Finds second-to-last 3D NetCDF file: `${SIMULATION_NAME}NNNN.nc`
   - Last file may be incomplete; second-to-last is safe restart point
3. Extracts time value from NetCDF using `ncdump`
4. Modifies SICOPOLIS header file (`sico_specs_${SIMULATION_NAME}.h`):
   ```c
   #define TIME_INIT0 '<extracted_time>'
   #define ANFDATNAME '<snapshot_file.nc>'
   #define ANF_DAT 3
   ```
5. Runs SICOPOLIS with restart configuration
6. On timeout, increments snapshot number and repeats

**Exit Behavior**:
- Exit code 85: Timeout, checkpoint created for restart
- Exit code 0: Normal completion, final output archived
- Other codes: Error, snapshot preserved for debugging

### Output Concatenation (sicoCheckpoints)

Python utility to concatenate outputs from multiple snapshot runs into continuous time series.

#### Usage
```bash
./sicoCheckpoints <output_path>
```

#### Process
1. **Cleanup**: Removes any existing concatenated files (`*1D*`, `*2D*`, `*3D*`)
2. **Iterate through snapshots**: Processes each numbered subdirectory (00000, 00001, ...)
3. **Extract time bounds**:
   - For intermediate snapshots: reads time from second-to-last 3D file
   - For final snapshot: uses all data
4. **Slice 1D data**: Extracts time series up to checkpoint time from `*_ser.nc`
5. **Slice 2D data**: Selects all 2D files (`*_2d_*.nc`) with time ≤ checkpoint
6. **Concatenate**: Uses NCO tools to merge sliced outputs
   - `ncecat`: Combines 2D files along time dimension
   - `ncrcat`: Concatenates 1D time series
7. **Cleanup**: Removes intermediate files, keeps final `${SIMULATION_NAME}_1D.nc` and `${SIMULATION_NAME}_2D.nc`

**Dependencies**:
- Python 3: numpy, xarray, netCDF4
- NCO tools: ncecat, ncrcat
- Extracting: tar, pigz

## Running Simulations on CHTC

### 1. Prepare Input
```bash
# Ensure sicopolis.zip exists in staging area
# /staging/<your_username>/sicopolis.zip
```

### 2. Configure Simulation
Edit `sico.sub`:
```
USERNAME = bob
SICOPOLIS_FILE = sicopolis.zip 
MAX_RUN_TIME = 6h
ANF_PATH_INIT = sico_in/grl
CORE_NB =1
RAM = 1GB
DISK = 10GB

...

SIMULATION_NAME = grl04_bm5_spinup02_holo_...  # Must match header file name
queue 1
```

### 3. Submit Job
```bash
condor_submit sico.sub
```

### 4. Monitor Progress
```bash
condor_q                  # Check job status
condor_tail -f <job_id>   # Follow output log
```

### 5. Retrieve and Process Results
```bash
# Download outputs from staging area: output_<cluster>_<process>_<simulation>.tar.gz
scp <your_username>@CHTC:/staging/<your_username>/output_<cluster>_<process>_<simulation>.tar.gz output.tar.gz


# Extract output archive:
mkdir output
tar -I "pigz -d -p 4" -xvf output.tar.gz -C output

# Extract and concatenate time series
./sicoCheckpoints output
```

## Configuration Notes

- **Path Configuration**: `exec.sh` automatically updates `sico_configs.sh` to use container paths:
  - `NETCDFHOME=/usr`
  - `LISHOME=/opt/lis`

- **Header Files**: Must exist in SICOPOLIS as `headers/sico_specs_${SIMULATION_NAME}.h`

- **Timeout Handling**: Exit code 85 is intercepted by HTCondor as checkpoint signal, not job failure

## Contact

**Nicolas B. Sartore**\
Research Assistant\
[Till Wagner Group](https://tillwagner.me)\
Department of Atmospheric and Oceanic Sciences\
University of Wisconsin-Madison, USA

- Website: [nsartore.me](https://nsartore.me)
- Email: [nsartore@wisc.edu](mailto:nsartore@wisc.edu)
- GitHub: [github.com/nicsar2](https://github.com/nicsar2)

For questions about this repository, feel free to open an issue or reach out by email.

#!/usr/bin/env python3

import os
import sys
import shutil
import glob
from pathlib import Path
import numpy as np
from netCDF4 import Dataset
import subprocess as sp
import xarray as xr

def sico_snap_concat(snap_path):

	if snap_path is None:
		raise ValueError("Error: expected 1 argument, got 0.")

	home_path = Path.cwd()
	if not home_path.exists():
		raise RuntimeError("Failed to get current directory")

	snap_path = Path(snap_path).resolve()
	if not snap_path.is_dir():
		raise RuntimeError("Snapshot directory missing")

	for pattern in ("*1D*", "*2D*", "*3D*"):
		for p in snap_path.glob(pattern):
			if p.is_dir():
				shutil.rmtree(p)
			else:
				p.unlink(missing_ok=True)

	subdirs = sorted([d for d in snap_path.iterdir() if d.is_dir()])
	for i, subdir in enumerate(subdirs):
		print(subdir)

		if not subdir.is_dir():
			raise RuntimeError(f"Error: snapshot subdirectory {subdir} does not exist!" )

		snapshotId = subdir.name

		os.chdir(subdir)

		for pattern in ("*.site", "*_site.nc"):
			for fname in glob.glob(pattern):
				os.remove(fname)

		files_1d = glob.glob("*_ser.nc")

		if len(files_1d) == 1:
			simName = files_1d[0].removesuffix("_ser.nc")
		else:
			os.chdir(home_path)
			raise RuntimeError(f"Expected exactly one *_ser.nc file, found {len(files_1d)}" )

		if not Path(f"{simName}0001.nc").is_file():
			os.chdir(home_path)
			raise RuntimeError(f"No 3D files in snapshot subdirectory {subdir}" )

		if i == len(subdirs) - 1:
			time = 1e99
		else:
			files_3D = sorted(glob.glob(f"{simName}0*.nc"))
			if len(files_3D) < 2:
				raise RuntimeError("Not enough NetCDF 3D files found")

			with Dataset(files_3D[-2], "r") as ds:
				time = ds.variables["time"][:]

		infile = f"{simName}_ser.nc"
		outfile = Path("..") / f"{snapshotId}_1D.nc"
		ds = xr.open_dataset(infile)
		ds_sliced = ds.sel(t=slice(None, time))
		ds_sliced.to_netcdf(outfile)
		ds.close()
		ds_sliced.close()

		files_2d = sorted(glob.glob("*_2d_*.nc"))
		selected_files = []
		for f in files_2d:
			with xr.open_dataset(f) as ds:
				file_tmax = float(ds.time)
			if file_tmax <= time:
				selected_files.append(f)
			else:
				break
		sp.run(["ncecat", "-u", "time", "-O", *selected_files, "-o", f"../{snapshotId}_2D.nc"], check=True)

	os.chdir(snap_path)

	files = sorted(glob.glob("*_1D.nc"))
	sp.run(["ncrcat", *files, f"{simName}_1D.nc"], check=True)
	for f in files:
		os.remove(f)

	files = sorted(glob.glob("*_2D.nc"))
	sp.run(["ncrcat", *files, f"{simName}_2D.nc"], check=True)
	for f in files:
		os.remove(f)

	os.chdir(home_path)

if __name__ == '__main__':
	sico_snap_concat(sys.argv[1])
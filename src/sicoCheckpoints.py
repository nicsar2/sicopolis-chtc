#!/usr/bin/env python3

import sys
import pathlib as pl
import subprocess as sb
import xarray as xr
import argparse as ap

def get2DList(path):
	if not isinstance(path, pl.Path):
		raise ValueError("Path wrong type")
	files = sorted(path.glob(f"{simName}_2d_[0-9][0-9][0-9][0-9].nc"))
	return files

def get3DList(path):
	if not isinstance(path, pl.Path):
		raise ValueError("Path wrong type")

	files = sorted(path.glob(f"{simName}[0-9][0-9][0-9][0-9].nc"))
	return files

def getSimulationName(path):
	if not isinstance(path, pl.Path):
		raise ValueError("Path wrong type")

	global simName
	hfiles = list(path.glob("*.h"))

	if len(hfiles)==0:
		print(f"No .h file in snapshot {snapshot.stem}, can not extract simulation name.")
		simName = input("Please input it manually here: ")
	elif len(hfiles)==1:
		hfile = hfiles[0]
		simName = hfile.stem.replace("sico_specs_", "")
	else:
		print(f"Multiple .h files in snapshot {snapshot.stem}, can not extract simulation name.")
		simName = input("Please input it manually here: ")

def verify_file_structure(path: pl.Path, extract2dFrom3d: bool):
	if not isinstance(path, pl.Path):
		raise ValueError("Path wrong type")

	is1Dok = True
	is2Dok = True
	is2Dfrom3D = False

	if not path.is_dir():
		raise ValueError(f"Main data path does not exist: {path}")

	snapshots = sorted([d for d in path.iterdir() if d.is_dir()])
	if not snapshots:
		raise ValueError(f"No snapshot subfolder in {path}")

	for idx, snapshot in enumerate(snapshots):
		if not snapshot.is_dir():
			raise ValueError(f"No data in snapshot subfolder in {snapshot}")

		if idx==0:
			getSimulationName(snapshot)

		if not (snapshot/(simName + "_ser.nc")).is_file():
			is1Dok = False
			print(f"No 1D data in snapshot subfolder in {snapshot.stem}, 1D will not be concatenated.")

		file_2d = get2DList(snapshot)
		if len(file_2d)<2:
			is2Dok = False
			print(f"No 2D data in snapshot subfolder in {snapshot.stem}, 2D will not be concatenated.")

		file_3d = get3DList(snapshot)
		if len(file_3d)<2 and len(snapshots)>1:
			raise ValueError(f"Error with 3D files, need at least 2 per snapshot")
		
		if len(file_3d)>2 and extract2dFrom3d:
			if not is2Dok:
				is2Dfrom3D = True
				print(f"2D will be extracted from 3D files.")
			else:
				print(f"Extract 2D from 3D is true, but 2D are present. They will be used instead.")


	return is1Dok, is2Dok, is2Dfrom3D

def removeOldFiles(path):
	if not isinstance(path, pl.Path):
		raise ValueError("Path wrong type")

	for pattern in ("*1D.nc*", "*2D.nc*", "*3D.nc*"):
		for file in path.glob(pattern):
			if file.is_file():
				file.unlink()

def removeUnusedFiles(path):
	if not isinstance(path, pl.Path):
		raise ValueError("Path wrong type")

	for pattern in ("*.site", "*_site.nc"):
		for file in path.glob(pattern):
			if file.is_file():
				file.unlink()

def sico_snap_concat(path, extract2dFrom3d):
	if isinstance(path, str):
		path = pl.Path(path)

	if not isinstance(path, pl.Path):
		raise ValueError("Path wrong type")
	path = path.resolve()

	is1Dok, is2Dok, is2Dfrom3D = verify_file_structure(path, extract2dFrom3d)

	removeOldFiles(path)

	snapshots = sorted([d for d in path.iterdir() if d.is_dir()])
	for i, snapshot in enumerate(snapshots):
		print(f"Concatenate: {snapshot.parent.name}/{snapshot.stem}")

		if not snapshot.is_dir():
			raise RuntimeError(f"Error: snapshot directory {snapshot} does not exist!" )

		removeUnusedFiles(snapshot)
		snapshotId = snapshot.name

		files3D = get3DList(snapshot)
		if i == len(snapshots) - 1:
			time = 1e99
		else:
			with xr.open_dataset(snapshot/files3D[-2]) as ds:
				time = float(ds.variables["time"])

		if is1Dok:
			file1D = snapshot/(simName + "_ser.nc")
			with xr.open_dataset(file1D) as ds:
				ds = ds.sel(t=slice(None, time))
				if i!=0:
					ds = ds.isel(t=slice(1, None))
				ds.to_netcdf(path / f"{snapshotId}_1D.nc")

		if is2Dok:
			files2D = get2DList(snapshot)
			selected_files = []
			for file in files2D:
				with xr.open_dataset(file) as ds:
					file_tmax = float(ds.time)
				if file_tmax <= time:
					selected_files.append(file)
				else:
					break
			if i!=0:
				selected_files = selected_files[1:]
			sb.run([
					"ncecat",
					"-u",
					"time",
					"-O",
					*selected_files,
					"-o",
					str(path/(snapshotId+"_2D.nc"))
				], check=True
			)

		if is2Dfrom3D:
			selected_files = []
			for file in files3D:
				with xr.open_dataset(file) as ds:
					file_tmax = float(ds.time)
				if file_tmax <= time:
					selected_files.append(file)
				else:
					break
			if i != 0:
				selected_files = selected_files[1:]

			with xr.open_dataset(selected_files[0]) as ds:
				vars_2d = []
				for var in ds.data_vars:
					dims = ds[var].dims
					print(dims)
					if len(dims)<=2:
						vars_2d.append(var)
				vars_string = ",".join(vars_2d)

			sb.run([
					"ncecat",
					"-u", "time",
					"-v", vars_string,
					"-O",
					*selected_files,
					"-o", str(path / (snapshotId + "_2D.nc"))
				], check=True
			)

	toConcatenate = []
	if is1Dok:
		toConcatenate.append("1D")
	if is2Dok or is2Dfrom3D:
		toConcatenate.append("2D")

	for dim in toConcatenate:
		files = sorted(path.glob(f"[0-9][0-9][0-9][0-9][0-9]_{dim}.nc"))
		sb.run(["ncrcat", *(str(f) for f in files), str(path / f"{simName}_{dim}.nc")], check=True )
		for file in files:
			file.unlink()


def main():

	pars = ap.ArgumentParser(
		description='SICOPOLIS output concatening script.'
	)

	pars.add_argument(
		'path',
		help='Path to the directory containing the snapshots.'
	)

	pars.add_argument(
		'-e', '--extract2dFrom3d',
		action='store_true',
		default=False,
		help='If 2d files are not present and 3d are, will extract the 2d data from the 3d files.'
	)

	args = pars.parse_args()

	sico_snap_concat(
		path=args.path,
		extract2dFrom3d=args.extract2dFrom3d
	)


if __name__ == '__main__':
	main()
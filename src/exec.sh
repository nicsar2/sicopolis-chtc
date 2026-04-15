#!/bin/bash
set -Exeuo pipefail

getLastSnapshotId() {

	if [[ "$#" -ne 1 ]]; then
		echo "Error: expected 1 arguments, got $#." >&2
		exit 2
	fi

	local name="$1"
	local files=()
	local list=()

	shopt -s nullglob
	files=( "${name:?}"[0-9][0-9][0-9][0-9].nc )
	shopt -u nullglob

	if [[ ${#files[@]} -lt 2 ]]; then
		echo "Error: fewer than two matching files for name '${name:?}'" >&2
		cleanup
		exit 1
	fi

	for f in "${files[@]}"; do
		[[ $f =~ ^${name:?}([0-9]{4})\.nc$ ]] || {
			echo "Error: unexpected filename format: $f" >&2
			cleanup
			exit 1
		}
		list+=( "${BASH_REMATCH[1]}" )
	done

	IFS=$'\n' read -r -d '' -a sorted < <(printf '%s\n' "${list[@]}" | sort && printf '\0')

	if [[ ${#sorted[@]} -lt 2 ]]; then
		echo "Error: sorting failed or insufficient data" >&2
		cleanup
		exit 1
	fi

	echo "${sorted[-2]}"
}

setHeader() {

	if [[ "$#" -ne 3 ]]; then
		echo "Error: expected 3 arguments, got $#." >&2
		cleanup
		exit 1
	fi

	local -r file="${1:?missing header file}"
	local -r var="${2:?missing variable name}"
	local -r newval="${3:?missing new value}"
	local count

	if [[ ! -f "$file" ]]; then
		echo "Error: file not found"
		cleanup
		exit 1
	fi

	count=$(grep -E "^[[:space:]]*#define[[:space:]]+${var:?}[[:space:]]+" "${file:?}" | wc -l)

	if [[ "${count:?}" -ne 1 ]]; then
		echo "Error: expected exactly one definition, found ${count:?}" >&2
		cleanup
		exit 1
	fi

	sed -i.bak -E "s|^([[:space:]]*#define[[:space:]]+${var:?}[[:space:]]+).*$|\1${newval:?}|" "${file:?}"

	rm -f "${file:?}.bak"
}

getNcTime() {
	if [[ "$#" -ne 1 ]]; then
		echo "Error: expected 3 arguments, got $#." >&2
		cleanup
		exit 1
	fi

	local -r file="$1"

	if [[ ! -f "${file:?}" ]]; then
		echo "Error: file does not exist" >&2
		cleanup
		exit 1
	fi

	local -r time_values=$(ncdump -v time "${file:?}" | awk '/time =/ {print $3}')

	if [[ -z "$time_values" ]]; then
		echo "Error: failed to extract time values" >&2
		cleanup
		exit 1
	fi

	echo "${time_values:?}"
}

getLastDir() {
	if [[ "$#" -ne 1 ]]; then
		echo "Error: expected 3 arguments, got $#." >&2
		cleanup
		exit 1
	fi

	local -r base_dir="${1:-.}"
	local last

	if [[ ! -d "${base_dir:?}" ]]; then
		echo "Error: not a directory" >&2
		cleanup
		exit 1
	fi

	last=$(find "${base_dir:?}" -maxdepth 1 -type d -printf '%f\n' \
		| grep -E '^[0-9]+$' \
		| sort -n \
		| tail -n 1)

	if [[ -z "${last:?}" ]]; then
		echo "Error: no numeric subdirectories found" >&2
		cleanup
		exit 1
	fi

	printf '%s\n' "${last:?}"
}

cleanup() {
	cd "${homePath:?}"

	if [[ ! -d "snapshot" ]]; then
		mkdir snapshot
	fi
	
	if [[ -d "${simPath}" ]]; then
		mv "${simPath}" snapshot/
	fi
	createOutputFile
}

createOutputFile() {
	tar --remove-files -I "pigz -p ${CORE_NB}" -cf "output_${OUTPUT_NAME:?}_${SIMULATION_NAME:?}.tar.gz" -C snapshot .
}

readonly SIMULATION_NAME="$1"
: "${SIMULATION_NAME:?No simulation name}"

readonly OUTPUT_NAME="$2"
: "${SIMULATION_NAME:?No simulation name}"

readonly SICOPOLIS_FILE="$3"
: "${SICOPOLIS_FILE:?No name for Sicopolis compressed folder}"
readonly sicoDirName="${SICOPOLIS_FILE%.*}"

readonly MAX_RUN_TIME="${4:-1d}"
readonly CORE_NB="${5:-1}"
readonly ANF_PATH_INIT="${6:-}"

readonly homePath="$(pwd)"
: "${homePath:?Failed to get current directory}"

readonly sicoPath="${homePath:?}/${sicoDirName:?}"
readonly simPath="${sicoPath:?}/sico_out/${SIMULATION_NAME:?}"

if [[ -f "${SICOPOLIS_FILE:?}" ]]; then
	unzip -qo "${SICOPOLIS_FILE:?}"
	rm "${SICOPOLIS_FILE:?}"
fi

if [[ ! -d "${sicoPath:?}" ]]; then
	echo "SICOPOLIS missing" >&2
	cleanup
	exit 1
fi

cd "${sicoPath:?}"
sed -i 's|^export[[:space:]]\+NETCDFHOME=[^[:space:]]\+|export NETCDFHOME=/usr |' "sico_configs.sh"
sed -i 's|^[[:space:]][[:space:]][[:space:]]\+LISHOME=[^[:space:]]\+|   LISHOME=/opt/lis |' "sico_configs.sh"

cd "${homePath:?}"
if [[ -d "snapshot" ]]; then
	readonly lastSnapshotNb=$(getLastDir "snapshot")
	readonly lastSnapshotNbNext=$(printf "%05d" $((10#"${lastSnapshotNb:?}" + 1)) )
	AnfPath="${homePath:?}/snapshot/${lastSnapshotNb:?}"
	cd "${AnfPath:?}"

	readonly ID=$(getLastSnapshotId "${SIMULATION_NAME:?}")
	readonly snapshotFile="${SIMULATION_NAME:?}${ID:?}.nc"
	readonly TM=$(getNcTime "${snapshotFile:?}")

	cd "${sicoPath:?}/headers"
	readonly configFile="sico_specs_${SIMULATION_NAME:?}.h"
	setHeader "${configFile:?}" "TIME_INIT0" "${TM:?}d0"
	setHeader "${configFile:?}" "ANFDATNAME" "'${snapshotFile:?}'"
	setHeader "${configFile:?}" "ANF_DAT" "3"

	cd "${sicoPath:?}"
	set +e
	timeout "${MAX_RUN_TIME:?}" ./sico.sh -fm "${SIMULATION_NAME:?}" -a "${AnfPath:?}" -o "${CORE_NB:?}"
	readonly timeout_exit_status="$?"
	set -e
	echo "sico.sh exited with: ${timeout_exit_status:?}"

else
	cd "${sicoPath:?}"
	if [ -z "${ANF_PATH_INIT}" ]; then
		set +e
		timeout "${MAX_RUN_TIME:?}" ./sico.sh -fm "${SIMULATION_NAME:?}" -o "${CORE_NB:?}"
		readonly timeout_exit_status="$?"
		set -e
		echo "sico.sh exited with: ${timeout_exit_status:?}"
	else
		set +e
		timeout "${MAX_RUN_TIME:?}" ./sico.sh -fm "${SIMULATION_NAME:?}" -o "${CORE_NB:?}" -a "${sicoPath:?}/${ANF_PATH_INIT:?}" 
		readonly timeout_exit_status="$?"
		set -e
		echo "sico.sh exited with: ${timeout_exit_status:?}"
	fi
	cd "${homePath:?}"
	mkdir snapshot
	readonly lastSnapshotNbNext="00000"
fi

cd "${homePath:?}"
mv "${simPath:?}" "snapshot/${lastSnapshotNbNext:?}"

if [ "${timeout_exit_status:?}" -eq 124 ]; then
	exit 85
else
	createOutputFile
	exit "${timeout_exit_status:?}"
fi


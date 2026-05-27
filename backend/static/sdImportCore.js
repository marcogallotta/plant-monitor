export const SD_TIME_GAP = 60 * 60 * 1000;

export function isImportablePhoto(filename) {
  const lower = filename.toLowerCase();
  return lower.endsWith('.jpg') || lower.endsWith('.jpeg') ||
         lower.endsWith('.orf') || lower.endsWith('.arw');
}

export function isRawPhoto(filename) {
  const lower = filename.toLowerCase();
  return lower.endsWith('.orf') || lower.endsWith('.arw');
}

export function sortCameraFiles(files) {
  return [...files].sort((a, b) => b.name.localeCompare(a.name));
}

// timestamps: array of lastModified values (ms), most-recent first.
// Returns index of first file in the older batch, or -1 if no boundary found.
export function detectSessionBoundary(timestamps, timeGap = SD_TIME_GAP) {
  for (let i = 0; i < timestamps.length - 1; i++) {
    const tA = timestamps[i];
    const tB = timestamps[i + 1];
    if (tA > 0 && tB > 0 && (tA - tB) > timeGap) return i + 1;
  }
  return -1;
}

// Scan a Uint8Array for the largest complete embedded JPEG (FF D8 FF ... FF D9).
// Returns {jpeg: Uint8Array|null, truncated: bool}.
// truncated=true means a JPEG started but its FFD9 end marker wasn't found.
export function scanForJpeg(bytes) {
  let best = null;
  let truncated = false;
  let i = 0;
  while (i < bytes.length - 3) {
    if (bytes[i] === 0xFF && bytes[i+1] === 0xD8 && bytes[i+2] === 0xFF) {
      let j = i + 2;
      let found = false;
      while (j < bytes.length - 1) {
        if (bytes[j] === 0xFF && bytes[j+1] === 0xD9) {
          const size = j + 2 - i;
          if (!best || size > best.size) best = {start: i, size};
          i = j + 2;
          found = true;
          break;
        }
        j++;
      }
      if (!found) { truncated = true; break; }
    } else {
      i++;
    }
  }
  const jpeg = best ? bytes.slice(best.start, best.start + best.size) : null;
  return {jpeg, truncated};
}

// Derive captured_at ISO string from EXIF data.
// Returns {iso: string, badge: 'ok'|'assumed'|'fallback'}.
// badge='ok' means a UTC offset was present so the timestamp is exact.
// badge='assumed' means no offset — browser timezone was assumed.
// badge='fallback' means no usable EXIF; file.lastModified was used.
export function deriveTimestamp(exif, file) {
  const dto = exif && (exif.DateTimeOriginal || exif.CreateDate);
  if (dto) {
    const d = dto instanceof Date ? dto : new Date(dto);
    if (!isNaN(d.getTime())) {
      const hasOffset = !!(exif && exif.OffsetTimeOriginal);
      return {iso: d.toISOString(), badge: hasOffset ? 'ok' : 'assumed'};
    }
  }
  return {iso: new Date(file.lastModified).toISOString(), badge: 'fallback'};
}

export function buildUploadFormData(uploadFile, originalName, capturedAt, photoType) {
  const fd = new FormData();
  fd.append('image', uploadFile, originalName);
  fd.append('captured_at', capturedAt);
  if (photoType) fd.append('photo_type', photoType);
  return fd;
}

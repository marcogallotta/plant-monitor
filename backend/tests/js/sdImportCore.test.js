import { describe, it, expect } from 'vitest';
import {
  isImportablePhoto, isRawPhoto, sortCameraFiles, detectSessionBoundary,
  scanForJpeg, deriveTimestamp, buildUploadFormData, SD_TIME_GAP,
} from '@/sdImportCore.js';

// ── isImportablePhoto ─────────────────────────────────────

describe('isImportablePhoto', () => {
  it.each(['.jpg', '.jpeg', '.orf', '.arw'])('accepts %s', ext => {
    expect(isImportablePhoto('DSC001' + ext)).toBe(true);
  });

  it('is case-insensitive', () => {
    expect(isImportablePhoto('DSC001.JPG')).toBe(true);
    expect(isImportablePhoto('DSC001.ARW')).toBe(true);
    expect(isImportablePhoto('DSC001.ORF')).toBe(true);
  });

  it.each(['.png', '.mp4', '.raw', '.dng', '.tiff'])('rejects %s', ext => {
    expect(isImportablePhoto('DSC001' + ext)).toBe(false);
  });

  it('rejects files with no extension', () => {
    expect(isImportablePhoto('DSC001')).toBe(false);
  });
});

// ── isRawPhoto ────────────────────────────────────────────

describe('isRawPhoto', () => {
  it.each(['.orf', '.arw'])('accepts %s', ext => {
    expect(isRawPhoto('DSC001' + ext)).toBe(true);
  });

  it('is case-insensitive', () => {
    expect(isRawPhoto('DSC001.ORF')).toBe(true);
    expect(isRawPhoto('DSC001.ARW')).toBe(true);
  });

  it.each(['.jpg', '.jpeg'])('rejects %s', ext => {
    expect(isRawPhoto('DSC001' + ext)).toBe(false);
  });
});

// ── sortCameraFiles ───────────────────────────────────────

describe('sortCameraFiles', () => {
  it('sorts by name descending', () => {
    const files = [{name: 'DSC001.jpg'}, {name: 'DSC003.jpg'}, {name: 'DSC002.jpg'}];
    const sorted = sortCameraFiles(files);
    expect(sorted.map(f => f.name)).toEqual(['DSC003.jpg', 'DSC002.jpg', 'DSC001.jpg']);
  });

  it('does not mutate the original array', () => {
    const files = [{name: 'DSC001.jpg'}, {name: 'DSC003.jpg'}];
    sortCameraFiles(files);
    expect(files[0].name).toBe('DSC001.jpg');
  });

  it('handles single-element array', () => {
    const files = [{name: 'DSC001.jpg'}];
    expect(sortCameraFiles(files)).toHaveLength(1);
  });
});

// ── detectSessionBoundary ─────────────────────────────────

describe('detectSessionBoundary', () => {
  const GAP = SD_TIME_GAP;

  it('returns -1 when all files are within the time gap', () => {
    const now = Date.now();
    const timestamps = [now, now - GAP / 2, now - GAP + 1];
    expect(detectSessionBoundary(timestamps)).toBe(-1);
  });

  it('returns the index of the first file in the older batch', () => {
    const now = Date.now();
    const timestamps = [now, now - GAP - 1000];
    expect(detectSessionBoundary(timestamps)).toBe(1);
  });

  it('returns the first boundary only when multiple gaps exist', () => {
    const now = Date.now();
    const timestamps = [now, now - GAP - 1000, now - GAP * 3, now - GAP * 5];
    expect(detectSessionBoundary(timestamps)).toBe(1);
  });

  it('returns -1 for empty or single-element array', () => {
    expect(detectSessionBoundary([])).toBe(-1);
    expect(detectSessionBoundary([Date.now()])).toBe(-1);
  });

  it('skips pairs where either timestamp is 0', () => {
    const now = Date.now();
    expect(detectSessionBoundary([now, 0, now - GAP * 3])).toBe(-1);
  });

  it('accepts a custom timeGap for testing', () => {
    const now = Date.now();
    const timestamps = [now, now - 2000]; // 2 second gap
    expect(detectSessionBoundary(timestamps, 1000)).toBe(1);
    expect(detectSessionBoundary(timestamps, 5000)).toBe(-1);
  });
});

// ── scanForJpeg ───────────────────────────────────────────

function makeJpeg(innerSize = 6) {
  // FF D8 FF [inner bytes] FF D9
  const bytes = new Uint8Array(innerSize + 5);
  bytes[0] = 0xFF; bytes[1] = 0xD8; bytes[2] = 0xFF; // SOI + marker start
  bytes[innerSize + 3] = 0xFF; bytes[innerSize + 4] = 0xD9; // EOI
  return bytes;
}

describe('scanForJpeg', () => {
  it('returns null for empty bytes', () => {
    const {jpeg, truncated} = scanForJpeg(new Uint8Array(0));
    expect(jpeg).toBeNull();
    expect(truncated).toBe(false);
  });

  it('returns null when no JPEG markers are present', () => {
    const {jpeg, truncated} = scanForJpeg(new Uint8Array([0x00, 0x01, 0x02, 0x03, 0x04]));
    expect(jpeg).toBeNull();
    expect(truncated).toBe(false);
  });

  it('finds a complete JPEG', () => {
    const jpeg = makeJpeg(4);
    const {jpeg: found, truncated} = scanForJpeg(jpeg);
    expect(found).not.toBeNull();
    expect(found.length).toBe(jpeg.length);
    expect(truncated).toBe(false);
  });

  it('finds a JPEG embedded in surrounding data', () => {
    const jpeg = makeJpeg(4);
    const buf = new Uint8Array([0x00, 0x00, ...jpeg, 0x00, 0x00]);
    const {jpeg: found} = scanForJpeg(buf);
    expect(found).not.toBeNull();
    expect(found.length).toBe(jpeg.length);
  });

  it('reports truncated when JPEG start found but no EOI', () => {
    // FF D8 FF [data] — no FF D9
    const bytes = new Uint8Array([0xFF, 0xD8, 0xFF, 0x00, 0x01, 0x02, 0x03]);
    const {jpeg, truncated} = scanForJpeg(bytes);
    expect(jpeg).toBeNull();
    expect(truncated).toBe(true);
  });

  it('returns the largest JPEG when multiple are present', () => {
    const small = makeJpeg(0);  // 5 bytes: FF D8 FF FF D9
    const large = makeJpeg(10); // 15 bytes
    const combined = new Uint8Array([...small, ...large]);
    const {jpeg} = scanForJpeg(combined);
    expect(jpeg.length).toBe(large.length);
  });
});

// ── deriveTimestamp ───────────────────────────────────────

describe('deriveTimestamp', () => {
  const fakeFile = {lastModified: new Date('2024-06-15T08:00:00.000Z').getTime()};

  it('returns badge=ok when DateTimeOriginal and OffsetTimeOriginal are present', () => {
    const exif = {DateTimeOriginal: new Date('2024-01-15T10:30:00.000Z'), OffsetTimeOriginal: '+02:00'};
    const {iso, badge} = deriveTimestamp(exif, fakeFile);
    expect(badge).toBe('ok');
    expect(iso).toBe('2024-01-15T10:30:00.000Z');
  });

  it('returns badge=assumed when DateTimeOriginal is present but no offset', () => {
    const exif = {DateTimeOriginal: new Date('2024-01-15T10:30:00.000Z')};
    const {badge} = deriveTimestamp(exif, fakeFile);
    expect(badge).toBe('assumed');
  });

  it('falls back to CreateDate when DateTimeOriginal is absent', () => {
    const exif = {CreateDate: new Date('2024-03-20T09:00:00.000Z')};
    const {iso, badge} = deriveTimestamp(exif, fakeFile);
    expect(badge).toBe('assumed');
    expect(iso).toBe('2024-03-20T09:00:00.000Z');
  });

  it('returns badge=fallback when exif is null', () => {
    const {iso, badge} = deriveTimestamp(null, fakeFile);
    expect(badge).toBe('fallback');
    expect(iso).toBe(new Date(fakeFile.lastModified).toISOString());
  });

  it('returns badge=fallback when DateTimeOriginal produces an invalid date', () => {
    const exif = {DateTimeOriginal: 'not-a-date'};
    const {badge} = deriveTimestamp(exif, fakeFile);
    expect(badge).toBe('fallback');
  });

  it('returns badge=fallback when exif is empty object', () => {
    const {badge} = deriveTimestamp({}, fakeFile);
    expect(badge).toBe('fallback');
  });
});

// ── buildUploadFormData ───────────────────────────────────

describe('buildUploadFormData', () => {
  const file = new File(['data'], 'extracted.jpg', {type: 'image/jpeg'});
  const ts   = '2024-01-15T10:00:00.000Z';

  it('sets captured_at', () => {
    const fd = buildUploadFormData(file, 'DSC001.JPG', ts, '');
    expect(fd.get('captured_at')).toBe(ts);
  });

  it('uses originalName as the image field filename', () => {
    const fd = buildUploadFormData(file, 'DSC001.ARW', ts, null);
    expect(fd.get('image').name).toBe('DSC001.ARW');
  });

  it('includes photo_type when provided', () => {
    const fd = buildUploadFormData(file, 'DSC001.JPG', ts, 'overview');
    expect(fd.get('photo_type')).toBe('overview');
  });

  it('omits photo_type when falsy', () => {
    expect(buildUploadFormData(file, 'DSC001.JPG', ts, '').has('photo_type')).toBe(false);
    expect(buildUploadFormData(file, 'DSC001.JPG', ts, null).has('photo_type')).toBe(false);
  });
});

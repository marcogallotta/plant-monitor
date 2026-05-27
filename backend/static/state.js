export const state = {
  // photos / grid
  allPhotos: [],
  photoA: null,
  photoB: null,
  allLocations: [],
  allUnits: [],

  // flicker
  flickerShowing: 'a',
  flickerTimer: null,

  // modal
  currentIndex: 0,
  currentPhotoId: null,
  currentRotation: 0,

  // notes
  currentNotes: [],
  pendingNote: null, // {x, y} for new note, or {noteId, x, y} for edit

  // zoom / pan
  zoom: 1,
  panX: 0,
  panY: 0,
  isPanning: false,
  panStart: null,
  wasDrag: false,
  isDrawingRect: false,
  rectStart: null, // {x, y} normalised image coords

  // timelapse
  tlIndex: 0,
  tlTimer: null,
};

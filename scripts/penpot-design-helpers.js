const C = {
  canvas: '#FBF8F2', white: '#FFFFFF', navy: '#0E3473', ink: '#102A5C',
  blue: '#2C67C8', gold: '#C9933A', red: '#A91422', muted: '#536481',
  line: '#E9E4DA', sand: '#F5EFE4', paleBlue: '#EAF2FB',
  green: '#19744D', paleGreen: '#E7F4EB', amber: '#9B5C05',
  paleAmber: '#F7EBD2', gray: '#68758A', paleGray: '#EEF0F3'
};
function rect(board, name, x, y, w, h, color, radius = 0) {
  const shape = penpot.createRectangle();
  shape.name = name; shape.x = board.x + x; shape.y = board.y + y;
  shape.resize(w, h); shape.fills = [{ fillColor: color }]; shape.borderRadius = radius;
  board.appendChild(shape); return shape;
}
function text(board, name, value, x, y, w, h, size = 14, weight = '400', color = C.ink, serif = false, align = 'left') {
  const shape = penpot.createText(value);
  shape.name = name; shape.x = board.x + x; shape.y = board.y + y;
  shape.growType = 'fixed'; shape.resize(w, h);
  shape.fontFamily = serif ? 'Noto Serif Georgian' : 'Inter Tight';
  shape.fontSize = String(size); shape.fontWeight = String(weight);
  shape.fills = [{ fillColor: color }]; shape.align = align;
  board.appendChild(shape); return shape;
}
function ellipse(board, name, x, y, size, color) {
  const shape = penpot.createEllipse();
  shape.name = name; shape.x = board.x + x; shape.y = board.y + y;
  shape.resize(size, size); shape.fills = [{ fillColor: color }];
  board.appendChild(shape); return shape;
}
function clean(board, names) {
  for (const shape of [...board.children]) if (names.some(name => shape.name === name || shape.name.startsWith(name + ' /'))) shape.remove();
}
function tap(shape, board) { shape.addInteraction('click', { type: 'navigate-to', destination: board }); }
storage.IS = { C, rect, text, ellipse, clean, tap };
return 'IntraSpot design helpers ready';

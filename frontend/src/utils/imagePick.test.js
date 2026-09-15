import { describe, expect, it } from 'vitest'

import { naturalPoint } from './imagePick'

describe('naturalPoint', () => {
  it('maps a fill point straight through', () => {
    const p = naturalPoint({
      x: 25,
      y: 50,
      rectWidth: 100,
      rectHeight: 100,
      naturalWidth: 10,
      naturalHeight: 10,
      fit: 'fill',
    })
    expect(p.u).toBeCloseTo(0.25)
    expect(p.v).toBeCloseTo(0.5)
  })

  it('accounts for a cover crop', () => {
    // A 100x100 image in a 200x100 box: scaled 2x and cropped top and bottom,
    // so the top edge of the box is a quarter into the image, not its start.
    const p = naturalPoint({
      x: 100,
      y: 0,
      rectWidth: 200,
      rectHeight: 100,
      naturalWidth: 100,
      naturalHeight: 100,
      fit: 'cover',
    })
    expect(p.u).toBeCloseTo(0.5)
    expect(p.v).toBeCloseTo(0.25)
  })

  it('accounts for a contain letterbox', () => {
    // A 100x100 image in a 200x100 box: drawn 100x100 centred, bars either side.
    const left = naturalPoint({
      x: 50,
      y: 0,
      rectWidth: 200,
      rectHeight: 100,
      naturalWidth: 100,
      naturalHeight: 100,
      fit: 'contain',
    })
    expect(left.u).toBeCloseTo(0)
    expect(left.v).toBeCloseTo(0)

    const middle = naturalPoint({
      x: 150,
      y: 50,
      rectWidth: 200,
      rectHeight: 100,
      naturalWidth: 100,
      naturalHeight: 100,
      fit: 'contain',
    })
    expect(middle.u).toBeCloseTo(1)
    expect(middle.v).toBeCloseTo(0.5)
  })

  it('clamps a click that lands outside the image', () => {
    const p = naturalPoint({
      x: -20,
      y: 300,
      rectWidth: 100,
      rectHeight: 100,
      naturalWidth: 100,
      naturalHeight: 100,
      fit: 'contain',
    })
    expect(p).toEqual({ u: 0, v: 1 })
  })

  it('falls back to the centre when the image has no size yet', () => {
    const p = naturalPoint({
      x: 1,
      y: 1,
      rectWidth: 0,
      rectHeight: 0,
      naturalWidth: 0,
      naturalHeight: 0,
    })
    expect(p).toEqual({ u: 0, v: 0 })
  })
})

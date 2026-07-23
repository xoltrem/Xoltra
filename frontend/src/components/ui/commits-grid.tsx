"use client";

import * as React from "react";
import { useRef } from "react";
import { useInView } from "framer-motion";
import { cn } from "@/lib/utils";
import type { CSSProperties } from "react";

// Adapted from https://21st.dev/@gonzalochale/components/commits-grid.
// Changes from the original beyond the text/size:
// 1. This project has no shadcn --card/--border tokens (Tailwind v4,
//    CSS-first theme, see globals.css). The original's `bg-card` and
//    bare `border` classes would resolve to nothing here, so both are
//    swapped for Xoltra's actual tokens.
// 2. Letter spacing (LETTER_ADVANCE) is 5, not 6. At 6, the L->T
//    boundary in "XOLTRA" showed an oversized gap, since both letters
//    are sparse away from their own edges. The X glyph is two straight
//    diagonals crossing at the center (see letterPatterns.X below).
// 3. Case is now preserved (cleanString/generateHighlightedCells no
//    longer force .toUpperCase()), and lowercase o/l/t/r/a glyphs were
//    added, so "Xoltra" renders with a capital X and lowercase rest
//    instead of forcing everything to capital-letter shapes.
// 3. The highlight/flash animation is CSS (animation-delay), which
//    autoplays on mount regardless of scroll position. It was finishing
//    (0.6s + up to 0.6s delay) long before a visitor scrolled down far
//    enough to actually see it, so by the time it was on screen it
//    looked static. Gated behind useInView(once: true) so it only
//    starts once the grid is actually visible.
export const CommitsGrid = ({
  text,
  className,
}: {
  text: string;
  className?: string;
}) => {
  const sectionRef = useRef<HTMLElement>(null);
  const isInView = useInView(sectionRef, { once: true, amount: 0.4 });

  const cleanString = (str: string): string => {
    // FIX: previously forced .toUpperCase() here, so "Xoltra" and "XOLTRA"
    // always rendered identically -- letterPatterns only had one (capital)
    // shape per letter. Preserving case now that lowercase o/l/t/r/a exist
    // below, so a capital X can render alongside lowercase letters.
    const withoutAccents = str
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "");

    const allowedChars = Object.keys(letterPatterns);
    return withoutAccents
      .split("")
      .filter((char) => allowedChars.includes(char))
      .join("");
  };

  const generateHighlightedCells = (text: string) => {
    const cleanedText = cleanString(text);
    const LETTER_ADVANCE = 5; // 6 made the L->T gap in "XOLTRA" look oversized (both letters are sparse near their outer edges), so back to 5

    const width = Math.max(cleanedText.length * LETTER_ADVANCE, LETTER_ADVANCE) + 1;

    let currentPosition = 1; // we start at 1 to leave space for the top border
    const highlightedCells: number[] = [];

    cleanedText
      .split("")
      .forEach((char) => {
        if (letterPatterns[char]) {
          const pattern = letterPatterns[char].map((pos) => {
            const row = Math.floor(pos / 50);
            const col = pos % 50;
            return (row + 1) * width + col + currentPosition;
          });
          highlightedCells.push(...pattern);
        }
        currentPosition += LETTER_ADVANCE;
      });

    return {
      cells: highlightedCells,
      width,
      height: 9, // 7+2 for the top and bottom borders
    };
  };

  const {
    cells: highlightedCells,
    width: gridWidth,
    height: gridHeight,
  } = generateHighlightedCells(text);

  const getRandomColor = () => {
    const commitColors = ["#48d55d", "#016d32", "#0d4429"];
    const randomIndex = Math.floor(Math.random() * commitColors.length);
    return commitColors[randomIndex];
  };

  const getRandomDelay = () => `${(Math.random() * 0.6).toFixed(1)}s`;
  const getRandomFlash = () => +(Math.random() < 0.3);

  return (
    <section
      ref={sectionRef}
      className={cn(
        // Original was max-w-xl (a card-sized widget), widened to a
        // hero-sized centerpiece per the "large title, takes up the
        // center of the page" brief. Cells are minmax(0,1fr), so they
        // scale up automatically as the container widens.
        "w-full max-w-5xl bg-[var(--color-panel-100)] border border-[var(--color-border-main)] grid p-2 sm:p-4 md:p-6 gap-1 sm:gap-1.5 md:gap-2 rounded-[10px] sm:rounded-[15px] md:rounded-[20px]",
        className
      )}
      style={{
        gridTemplateColumns: `repeat(${gridWidth}, minmax(0, 1fr))`,
        gridTemplateRows: `repeat(${gridHeight}, minmax(0, 1fr))`,
      }}
    >
      {Array.from({ length: gridWidth * gridHeight }).map((_, index) => {
        const isHighlighted = highlightedCells.includes(index);
        const shouldFlash = !isHighlighted && getRandomFlash();

        return (
          <div
            key={index}
            className={cn(
              "border border-[var(--color-border-main)] h-full w-full aspect-square rounded-[4px] sm:rounded-[3px]",
              isInView && isHighlighted ? "animate-highlight" : "",
              isInView && shouldFlash ? "animate-flash" : "",
              !isHighlighted && !shouldFlash ? "bg-[var(--color-panel-100)]" : ""
            )}
            style={
              {
                animationDelay: getRandomDelay(),
                "--highlight": getRandomColor(),
              } as CSSProperties
            }
          />
        );
      })}
    </section>
  );
};

const letterPatterns: { [key: string]: number[] } = {
  A: [
    1, 2, 3, 50, 100, 150, 200, 250, 300, 54, 104, 154, 204, 254, 304, 151, 152,
    153,
  ],
  B: [
    0, 1, 2, 3, 4, 50, 100, 150, 151, 200, 250, 300, 301, 302, 303, 304, 54,
    104, 152, 153, 204, 254, 303,
  ],
  C: [0, 1, 2, 3, 4, 50, 100, 150, 200, 250, 300, 301, 302, 303, 304],
  D: [
    0, 1, 2, 3, 50, 100, 150, 200, 250, 300, 301, 302, 54, 104, 154, 204, 254,
    303,
  ],
  E: [0, 1, 2, 3, 4, 50, 100, 150, 200, 250, 300, 301, 302, 303, 304, 151, 152],
  F: [0, 1, 2, 3, 4, 50, 100, 150, 200, 250, 300, 151, 152, 153],
  G: [
    0, 1, 2, 3, 4, 50, 100, 150, 200, 250, 300, 301, 302, 303, 153, 204, 154,
    304, 254,
  ],
  H: [
    0, 50, 100, 150, 200, 250, 300, 151, 152, 153, 4, 54, 104, 154, 204, 254,
    304,
  ],
  I: [0, 1, 2, 3, 4, 52, 102, 152, 202, 252, 300, 301, 302, 303, 304],
  J: [0, 1, 2, 3, 4, 52, 102, 152, 202, 250, 252, 302, 300, 301],
  K: [0, 4, 50, 100, 150, 200, 250, 300, 151, 152, 103, 54, 203, 254, 304],
  // Shifted one column right within its own box (was col0 vertical stroke +
  // cols0-4 foot) -- closes some of the empty space toward the next letter,
  // per request to "move the L a space block ahead".
  L: [1, 51, 101, 151, 201, 251, 301, 302, 303, 304],
  M: [
    0, 50, 100, 150, 200, 250, 300, 51, 102, 53, 4, 54, 104, 154, 204, 254, 304,
  ],
  N: [
    0, 50, 100, 150, 200, 250, 300, 51, 102, 153, 204, 4, 54, 104, 154, 204,
    254, 304,
  ],
  Ñ: [
    0, 50, 100, 150, 200, 250, 300, 51, 102, 153, 204, 4, 54, 104, 154, 204,
    254, 304,
  ],
  O: [1, 2, 3, 50, 100, 150, 200, 250, 301, 302, 303, 54, 104, 154, 204, 254],
  P: [0, 50, 100, 150, 200, 250, 300, 1, 2, 3, 54, 104, 151, 152, 153],
  Q: [
    1, 2, 3, 50, 100, 150, 200, 250, 301, 302, 54, 104, 154, 204, 202, 253, 304,
  ],
  R: [
    0, 50, 100, 150, 200, 250, 300, 1, 2, 3, 54, 104, 151, 152, 153, 204, 254,
    304,
  ],
  S: [1, 2, 3, 4, 50, 100, 151, 152, 153, 204, 254, 300, 301, 302, 303],
  T: [0, 1, 2, 3, 4, 52, 102, 152, 202, 252, 302],
  U: [0, 50, 100, 150, 200, 250, 301, 302, 303, 4, 54, 104, 154, 204, 254],
  V: [0, 50, 100, 150, 200, 251, 302, 4, 54, 104, 154, 204, 253],
  W: [
    0, 50, 100, 150, 200, 250, 301, 152, 202, 252, 4, 54, 104, 154, 204, 254,
    303,
  ],
  // Straightest achievable X at this grid resolution: two diagonals from
  // each corner, meeting at a single center point (row 3). Kept as thin,
  // single-pixel-per-row lines rather than widened/bolded -- widening it
  // (an earlier attempt used cols 0,1 and 3,4 near the top/bottom) breaks
  // the straight-line look by fattening the ends into a curve/taper.
  X: [0, 4, 51, 53, 101, 103, 152, 201, 203, 251, 253, 300, 304],
  Y: [0, 50, 101, 152, 202, 252, 302, 4, 54, 103],
  Z: [0, 1, 2, 3, 4, 54, 103, 152, 201, 250, 300, 301, 302, 303, 304],
  "0": [1, 2, 3, 50, 100, 150, 200, 250, 301, 302, 303, 54, 104, 154, 204, 254],
  "1": [1, 52, 102, 152, 202, 252, 302, 0, 2, 300, 301, 302, 303, 304],
  "2": [0, 1, 2, 3, 54, 104, 152, 153, 201, 250, 300, 301, 302, 303, 304],
  "3": [0, 1, 2, 3, 54, 104, 152, 153, 204, 254, 300, 301, 302, 303],
  "4": [0, 50, 100, 150, 4, 54, 104, 151, 152, 153, 154, 204, 254, 304],
  "5": [0, 1, 2, 3, 4, 50, 100, 151, 152, 153, 204, 254, 300, 301, 302, 303],
  "6": [
    1, 2, 3, 50, 100, 150, 151, 152, 153, 200, 250, 301, 302, 204, 254, 303,
  ],
  "7": [0, 1, 2, 3, 4, 54, 103, 152, 201, 250, 300],
  "8": [
    1, 2, 3, 50, 100, 151, 152, 153, 200, 250, 301, 302, 303, 54, 104, 204, 254,
  ],
  "9": [1, 2, 3, 50, 100, 151, 152, 153, 154, 204, 254, 304, 54, 104],
  " ": [],

  // Lowercase glyphs, added so a word can mix a capital first letter with
  // lowercase rest (e.g. "Xoltra") -- previously only capital shapes
  // existed, so case had no visual effect at all. These sit on the same
  // baseline (row 6) as the capitals. Letters with no ascender (o, r, a)
  // only occupy the lower x-height rows (3-6); l and t keep a tall
  // ascender since that's how those letters actually look. This is a
  // first pass without a way to preview the render -- expect it may need
  // a follow-up tweak once you see it live.
  o: [151, 152, 153, 200, 204, 250, 254, 301, 302, 303],
  l: [1, 51, 101, 151, 201, 251, 301],
  t: [52, 101, 102, 103, 152, 202, 252, 302, 303],
  r: [151, 152, 153, 201, 251, 301],
  a: [151, 152, 153, 200, 203, 250, 253, 301, 302, 303],
};

import { render, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { BrandMark } from "./BrandMark";
describe("brand logo", () => {
  it("keeps a fallback visible until a valid image loads", () => {
    const { container } = render(<BrandMark />);
    const image = container.querySelector("img")!;
    const fallback = container.querySelector(".brand-fallback")!;
    expect(image.getAttribute("src")).toBe("/logo.png");
    expect(image).not.toBeVisible();
    expect(fallback).toBeVisible();
    fireEvent.error(image);
    expect(image).not.toBeVisible();
    expect(fallback).toBeVisible();
    fireEvent.load(image);
    expect(image).toBeVisible();
    expect(fallback).not.toBeVisible();
  });
});

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import ApplicationAnswers from "./ApplicationAnswers";

describe("ApplicationAnswers", () => {
  it("renders eligibility + EEO fields and emits changes", () => {
    const onChange = vi.fn();
    render(<ApplicationAnswers value={{ eligibility: {}, eeo: {} }} onChange={onChange} />);
    expect(screen.getByLabelText(/authorized to work/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/gender/i)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/authorized to work/i), { target: { value: "yes" } });
    expect(onChange).toHaveBeenCalled();
  });

  it("EEO selects include a decline option", () => {
    render(<ApplicationAnswers value={{ eligibility: {}, eeo: {} }} onChange={() => {}} />);
    expect(screen.getAllByText(/decline to self-identify/i).length).toBeGreaterThan(0);
  });
});

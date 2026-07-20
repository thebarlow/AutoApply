import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import AtsChip from './AtsChip';

describe('AtsChip', () => {
  it('shows Easy Apply for in-platform jobs', () => {
    render(<AtsChip atsType="easy_apply" easyApply={true} />);
    expect(screen.getByText(/easy apply/i)).toBeInTheDocument();
  });
  it('shows the ATS name for a recognized ATS', () => {
    render(<AtsChip atsType="greenhouse" easyApply={false} />);
    expect(screen.getByText(/greenhouse/i)).toBeInTheDocument();
  });
  it('shows Resolving… for an unresolved external job', () => {
    render(<AtsChip atsType={null} easyApply={false} />);
    expect(screen.getByText(/resolving/i)).toBeInTheDocument();
  });
  it('renders nothing when there is no apply signal', () => {
    const { container } = render(<AtsChip atsType={null} easyApply={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});

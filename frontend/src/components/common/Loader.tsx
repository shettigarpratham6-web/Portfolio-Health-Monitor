import React from 'react';
import styled from 'styled-components';

interface LoaderProps {
  scale?: number;
  className?: string;
}

const Loader: React.FC<LoaderProps> = ({ scale, className }) => {
  const scaledWidth = scale ? 180 * scale : undefined;
  const scaledHeight = scale ? 180 * scale : undefined;

  return (
    <div
      className={className}
      style={
        scale
          ? {
              width: `${scaledWidth}px`,
              height: `${scaledHeight}px`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              overflow: 'visible',
            }
          : undefined
      }
    >
      <StyledWrapper
        style={
          scale
            ? {
                transform: `scale(${scale})`,
                transformOrigin: 'center center',
              }
            : undefined
        }
      >
        <div className="loader-wrapper">
          <span className="loader-letter">C</span>
          <span className="loader-letter">o</span>
          <span className="loader-letter">n</span>
          <span className="loader-letter">n</span>
          <span className="loader-letter">e</span>
          <span className="loader-letter">c</span>
          <span className="loader-letter">t</span>
          <span className="loader-letter">i</span>
          <span className="loader-letter">n</span>
          <span className="loader-letter">g</span>
          <div className="loader" />
        </div>
      </StyledWrapper>
    </div>
  );
};

const StyledWrapper = styled.div`
  .loader-wrapper {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 180px;
    height: 180px;
    font-family: "Inter", sans-serif;
    font-size: 1.2em;
    font-weight: 300;
    color: white;
    border-radius: 50%;
    background: radial-gradient(
      circle at center,
      rgba(6, 78, 59, 0.45) 0%,
      rgba(2, 44, 34, 0.85) 60%,
      rgba(4, 18, 14, 0.98) 100%
    );
    box-shadow:
      0 0 35px -5px rgba(16, 185, 129, 0.35),
      0 0 15px -3px rgba(6, 182, 212, 0.25);
    user-select: none;
  }

  .loader {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    aspect-ratio: 1 / 1;
    border-radius: 50%;
    background-color: transparent;
    animation: loader-rotate 1.5s linear infinite;
    z-index: 0;
  }

  @keyframes loader-rotate {
    0% {
      transform: rotate(90deg);
      box-shadow:
        0 10px 20px 0 #fff inset,
        0 20px 30px 0 #34d399 inset,
        0 60px 60px 0 #064e3b inset;
    }
    50% {
      transform: rotate(270deg);
      box-shadow:
        0 10px 20px 0 #fff inset,
        0 20px 20px 0 #06b6d4 inset,
        0 40px 60px 0 #022c22 inset;
    }
    100% {
      transform: rotate(450deg);
      box-shadow:
        0 10px 20px 0 #fff inset,
        0 20px 30px 0 #34d399 inset,
        0 60px 60px 0 #064e3b inset;
    }
  }

  .loader-letter {
    display: inline-block;
    opacity: 0.4;
    transform: translateY(0);
    animation: loader-letter-anim 1.5s infinite;
    z-index: 1;
    border-radius: 50ch;
    border: none;
  }

  .loader-letter:nth-child(1) {
    animation-delay: 0s;
  }
  .loader-letter:nth-child(2) {
    animation-delay: 0.15s;
  }
  .loader-letter:nth-child(3) {
    animation-delay: 0.3s;
  }
  .loader-letter:nth-child(4) {
    animation-delay: 0.45s;
  }
  .loader-letter:nth-child(5) {
    animation-delay: 0.6s;
  }
  .loader-letter:nth-child(6) {
    animation-delay: 0.75s;
  }
  .loader-letter:nth-child(7) {
    animation-delay: 0.9s;
  }
  .loader-letter:nth-child(8) {
    animation-delay: 1.05s;
  }
  .loader-letter:nth-child(9) {
    animation-delay: 1.2s;
  }
  .loader-letter:nth-child(10) {
    animation-delay: 1.35s;
  }

  @keyframes loader-letter-anim {
    0%,
    100% {
      opacity: 0.4;
      transform: translateY(0);
    }
    20% {
      opacity: 1;
      transform: scale(1.15);
    }
    40% {
      opacity: 0.7;
      transform: translateY(0);
    }
  }
`;

export default Loader;
export { Loader };

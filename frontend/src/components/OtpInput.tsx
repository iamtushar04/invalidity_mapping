import React, { useRef } from "react";

const OTP_LENGTH = 6;

interface OtpInputProps {
  otp: string[];
  setOtp: (otp: string[]) => void;
}

const OtpInput: React.FC<OtpInputProps> = ({ otp, setOtp }) => {
  const inputsRef = useRef<(HTMLInputElement | null)[]>([]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>, index: number) => {
    const value = e.target.value;
    if (!/^[0-9]*$/.test(value)) return;

    if (value.length === 1) {
      const newOtp = [...otp];
      newOtp[index] = value;
      setOtp(newOtp);
      if (index < OTP_LENGTH - 1) inputsRef.current[index + 1]?.focus();
    } else if (value.length === 0) {
      const newOtp = [...otp];
      newOtp[index] = "";
      setOtp(newOtp);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>, index: number) => {
    if (e.key === "Backspace" && !otp[index] && index > 0) {
      inputsRef.current[index - 1]?.focus();
    }
  };

  const handlePaste = (e: React.ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    const pasteData = e.clipboardData.getData("text").trim().slice(0, OTP_LENGTH);
    const newOtp = [...otp];

    pasteData.split("").forEach((char, idx) => {
      if (/^[0-9]$/.test(char) && idx < OTP_LENGTH) {
        newOtp[idx] = char;
        if (inputsRef.current[idx]) {
          inputsRef.current[idx]!.value = char;
        }
      }
    });

    setOtp(newOtp);
    const lastIndex = Math.min(pasteData.length, OTP_LENGTH - 1);
    inputsRef.current[lastIndex]?.focus();
  };

  return (
    <div className="flex justify-between gap-2 mb-6">
      {[...Array(OTP_LENGTH)].map((_, index) => (
        <input
          key={index}
          type="text"
          maxLength={1}
          value={otp[index] || ""}
          className="w-12 h-12 text-center text-xl font-bold bg-slate-900 border border-slate-800 rounded-xl focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition text-slate-100 placeholder-slate-600 shadow-inner"
          ref={(el) => {
            inputsRef.current[index] = el;
          }}
          onChange={(e) => handleChange(e, index)}
          onKeyDown={(e) => handleKeyDown(e, index)}
          onPaste={handlePaste}
        />
      ))}
    </div>
  );
};

export default OtpInput;

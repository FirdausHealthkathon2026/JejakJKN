import type {ReactElement} from "react";

export type QrScannerPanelProps = {
  disabled?: boolean;
  resetKey: string;
  onDecoded(value: string): void;
  onError(message: string): void;
};

export declare function validateQrImage(file: File, width: number, height: number): string | null;
export declare function QrScannerPanel(props: QrScannerPanelProps): ReactElement;

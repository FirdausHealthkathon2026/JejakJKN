export type LocalRecord = {record_id: string; external_record_id: string; jenis: string; kode: string; status: string};
export type SyncStatus = {encounter_id: string; sync_status: string; last_error: string | null; pending: number; failed: number; delivered: number; records: LocalRecord[]};
export type LocalClinicalInput = {jenis: string; kode: string; id_rekam: string; jumlah?: number; satuan?: string};

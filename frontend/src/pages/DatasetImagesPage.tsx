import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckSquare, Download, ImageDown, RefreshCw, Square, Trash2 } from 'lucide-react'
import { deleteDatasetImage, fetchDatasetImages, type DatasetImage } from '@/api/inspectionApi'

function imageKey(image: DatasetImage): string {
  return `${image.deviceId}/${image.session}/${image.filename}`
}

function formatTimestamp(iso?: string): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('ko-KR', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return iso
  }
}

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes)) return '—'
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`
}

function downloadOne(image: DatasetImage) {
  const anchor = document.createElement('a')
  anchor.href = image.downloadUrl
  anchor.download = image.filename
  anchor.rel = 'noopener'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
}

export default function DatasetImagesPage() {
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(() => new Set())
  const [fromDateTime, setFromDateTime] = useState('')
  const [toDateTime, setToDateTime] = useState('')
  const queryClient = useQueryClient()
  const imagesQ = useQuery({
    queryKey: ['dataset-images'],
    queryFn: fetchDatasetImages,
    refetchInterval: 10_000,
  })

  const images = imagesQ.data ?? []
  const filteredImages = useMemo(() => {
    const fromMs = fromDateTime ? new Date(fromDateTime).getTime() : null
    const toMs = toDateTime ? new Date(toDateTime).getTime() : null
    return images.filter((image) => {
      const createdMs = new Date(image.createdAt).getTime()
      if (Number.isNaN(createdMs)) return true
      if (fromMs != null && createdMs < fromMs) return false
      if (toMs != null && createdMs > toMs) return false
      return true
    })
  }, [fromDateTime, images, toDateTime])
  const selectedImages = useMemo(
    () => filteredImages.filter((image) => selectedKeys.has(imageKey(image))),
    [filteredImages, selectedKeys]
  )
  const allSelected =
    filteredImages.length > 0 && filteredImages.every((image) => selectedKeys.has(imageKey(image)))

  const deleteM = useMutation({
    mutationFn: async (targets: DatasetImage[]) => {
      await Promise.all(targets.map(deleteDatasetImage))
    },
    onSuccess: () => {
      setSelectedKeys(new Set())
      queryClient.invalidateQueries({ queryKey: ['dataset-images'] })
    },
  })

  const toggleOne = (key: string) => {
    setSelectedKeys((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const selectAll = () => {
    setSelectedKeys(new Set(filteredImages.map(imageKey)))
  }

  const clearAll = () => {
    setSelectedKeys(new Set())
  }

  const downloadSelected = () => {
    selectedImages.forEach((image, index) => {
      window.setTimeout(() => downloadOne(image), index * 250)
    })
  }

  const deleteSelected = () => {
    if (selectedImages.length === 0 || deleteM.isPending) return
    const ok = window.confirm(`선택한 데이터셋 이미지 ${selectedImages.length}장을 삭제할까요?`)
    if (ok) deleteM.mutate(selectedImages)
  }

  const clearFilters = () => {
    setFromDateTime('')
    setToDateTime('')
  }

  return (
    <div className="h-full overflow-y-auto p-6 space-y-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 className="text-lg font-bold text-white">데이터셋 이미지</h2>
          <p className="mt-0.5 text-xs text-gray-500">
            서버에 보관된 라벨링용 원본 이미지를 선택해서 내려받습니다.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => imagesQ.refetch()}
            className="inline-flex items-center gap-2 rounded-md border border-gray-700 px-3 py-2 text-xs font-semibold text-gray-200 transition-colors hover:bg-gray-800"
          >
            <RefreshCw size={14} />
            새로고침
          </button>
          <button
            onClick={selectAll}
            disabled={filteredImages.length === 0 || allSelected}
            className="inline-flex items-center gap-2 rounded-md border border-gray-700 px-3 py-2 text-xs font-semibold text-gray-200 transition-colors hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-45"
          >
            <CheckSquare size={14} />
            전체 선택
          </button>
          <button
            onClick={clearAll}
            disabled={selectedKeys.size === 0}
            className="inline-flex items-center gap-2 rounded-md border border-gray-700 px-3 py-2 text-xs font-semibold text-gray-200 transition-colors hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-45"
          >
            <Square size={14} />
            전체 취소
          </button>
          <button
            onClick={downloadSelected}
            disabled={selectedImages.length === 0}
            className="inline-flex items-center gap-2 rounded-md border border-indigo-500/60 bg-indigo-500/15 px-3 py-2 text-xs font-semibold text-indigo-100 transition-colors hover:bg-indigo-500/25 disabled:cursor-not-allowed disabled:opacity-45"
          >
            <Download size={14} />
            선택 다운로드 {selectedImages.length > 0 ? `(${selectedImages.length})` : ''}
          </button>
          <button
            onClick={deleteSelected}
            disabled={selectedImages.length === 0 || deleteM.isPending}
            className="inline-flex items-center gap-2 rounded-md border border-red-500/60 bg-red-500/10 px-3 py-2 text-xs font-semibold text-red-100 transition-colors hover:bg-red-500/20 disabled:cursor-not-allowed disabled:opacity-45"
          >
            <Trash2 size={14} />
            선택 삭제 {selectedImages.length > 0 ? `(${selectedImages.length})` : ''}
          </button>
        </div>
      </div>

      <section className="rounded-xl border border-gray-800 bg-gray-900">
        <div className="flex flex-col gap-4 border-b border-gray-800 px-5 py-4 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex items-center gap-2 text-gray-200">
            <ImageDown size={16} />
            <h3 className="text-sm font-semibold">서버 보관 이미지</h3>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1">
              <span className="text-[11px] font-semibold text-gray-500">시작 시각</span>
              <input
                type="datetime-local"
                value={fromDateTime}
                onChange={(e) => setFromDateTime(e.target.value)}
                className="h-9 rounded-md border border-gray-700 bg-gray-950 px-2 text-xs text-gray-200 outline-none focus:border-indigo-500"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-[11px] font-semibold text-gray-500">종료 시각</span>
              <input
                type="datetime-local"
                value={toDateTime}
                onChange={(e) => setToDateTime(e.target.value)}
                className="h-9 rounded-md border border-gray-700 bg-gray-950 px-2 text-xs text-gray-200 outline-none focus:border-indigo-500"
              />
            </label>
            <button
              onClick={clearFilters}
              disabled={!fromDateTime && !toDateTime}
              className="h-9 rounded-md border border-gray-700 px-3 text-xs font-semibold text-gray-200 transition-colors hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-45"
            >
              필터 초기화
            </button>
            <span className="pb-2 text-xs text-gray-500">
              전체 {images.length}장 · 조회 {filteredImages.length}장 · 선택 {selectedImages.length}장
            </span>
          </div>
        </div>

        {imagesQ.isLoading ? (
          <p className="py-10 text-center text-xs text-gray-500">데이터셋 이미지 불러오는 중...</p>
        ) : images.length === 0 ? (
          <p className="py-10 text-center text-xs text-gray-500">
            아직 서버에 저장된 라벨링 이미지가 없습니다.
          </p>
        ) : filteredImages.length === 0 ? (
          <p className="py-10 text-center text-xs text-gray-500">
            선택한 저장 시각 범위에 해당하는 이미지가 없습니다.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] text-sm">
              <thead>
                <tr className="bg-gray-900/60 text-left">
                  <th className="w-12 px-3 py-2">
                    <button
                      onClick={allSelected ? clearAll : selectAll}
                      className="inline-flex h-7 w-7 items-center justify-center rounded-md text-gray-300 hover:bg-gray-800 hover:text-white"
                      aria-label={allSelected ? '전체 취소' : '전체 선택'}
                    >
                      {allSelected ? <CheckSquare size={16} /> : <Square size={16} />}
                    </button>
                  </th>
                  {['세션', '파일명', '디바이스', '크기', '저장 시각', '다운로드'].map((h) => (
                    <th
                      key={h}
                      className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-gray-500"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800/60">
                {filteredImages.map((image) => {
                  const key = imageKey(image)
                  const checked = selectedKeys.has(key)
                  return (
                    <tr key={key} className={checked ? 'bg-indigo-950/25' : 'bg-gray-900/40'}>
                      <td className="px-3 py-2">
                        <button
                          onClick={() => toggleOne(key)}
                          className="inline-flex h-7 w-7 items-center justify-center rounded-md text-gray-300 hover:bg-gray-800 hover:text-white"
                          aria-label={checked ? '선택 해제' : '선택'}
                        >
                          {checked ? <CheckSquare size={16} /> : <Square size={16} />}
                        </button>
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-gray-300">{image.session}</td>
                      <td className="px-3 py-2 font-mono text-xs text-gray-300">{image.filename}</td>
                      <td className="px-3 py-2 font-mono text-xs text-gray-400">{image.deviceId}</td>
                      <td className="px-3 py-2 text-xs text-gray-400">{formatBytes(image.sizeBytes)}</td>
                      <td className="px-3 py-2 font-mono text-xs text-gray-400">
                        {formatTimestamp(image.createdAt)}
                      </td>
                      <td className="px-3 py-2">
                        <a
                          href={image.downloadUrl}
                          download={image.filename}
                          className="inline-flex items-center gap-1.5 rounded-md border border-gray-700 px-2.5 py-1.5 text-xs font-semibold text-gray-200 transition-colors hover:bg-gray-800"
                        >
                          <Download size={13} />
                          받기
                        </a>
                        <button
                          onClick={() => {
                            const ok = window.confirm(`${image.filename} 파일을 삭제할까요?`)
                            if (ok) deleteM.mutate([image])
                          }}
                          disabled={deleteM.isPending}
                          className="ml-2 inline-flex items-center gap-1.5 rounded-md border border-red-900/70 px-2.5 py-1.5 text-xs font-semibold text-red-200 transition-colors hover:bg-red-950/40 disabled:cursor-not-allowed disabled:opacity-45"
                        >
                          <Trash2 size={13} />
                          삭제
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}

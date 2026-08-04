import axiosInstance from "@/api/axios"

/**
 * Fetch a file from `url` (via axiosInstance, so auth headers are attached)
 * and trigger a browser download. Reads the filename from the response's
 * Content-Disposition header when present, falling back to `filenameFallback`.
 */
export async function downloadFile(url: string, filenameFallback: string): Promise<void> {
  const response = await axiosInstance.get(url, { responseType: "blob" })

  const disposition: string | undefined = response.headers["content-disposition"]
  const match = disposition?.match(/filename="?([^"]+)"?/)
  const filename = match?.[1] ?? filenameFallback

  const blobUrl = URL.createObjectURL(response.data as Blob)
  const link = document.createElement("a")
  link.href = blobUrl
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(blobUrl)
}

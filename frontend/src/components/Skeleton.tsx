export function SkeletonBar({ width = '100%', height = 14 }: { width?: string | number; height?: number }) {
  return <div className="skeleton" style={{ width, height, borderRadius: 6 }} />
}

export function SkeletonTableRows({ rows = 4, cols = 3 }: { rows?: number; cols?: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, r) => (
        <tr key={r}>
          {Array.from({ length: cols }).map((_, c) => (
            <td key={c}>
              <SkeletonBar width={c === 0 ? '70%' : '85%'} />
            </td>
          ))}
        </tr>
      ))}
    </>
  )
}

export function SkeletonDeviceCards({ count = 6 }: { count?: number }) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <div className="device-node" key={i}>
          <div className="device-node-head">
            <div className="skeleton" style={{ width: 34, height: 34, borderRadius: 10 }} />
            <div style={{ flex: 1 }}>
              <SkeletonBar width="60%" height={13} />
              <div style={{ height: 6 }} />
              <SkeletonBar width="35%" height={10} />
            </div>
          </div>
          <div className="device-meta">
            <SkeletonBar width="90%" height={11} />
          </div>
          <SkeletonBar width="100%" height={11} />
        </div>
      ))}
    </>
  )
}

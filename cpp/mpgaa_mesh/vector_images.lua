-- Keep PNG links in the readable Markdown, and use vector plots for the PDF.
function Image(item)
  item.src = item.src:gsub("%.png$", ".pdf")
  return item
end

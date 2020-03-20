import cv2
import numpy as np
import imutils

def cornerIn(curr, image_points):
  for x, y in image_points:
    if abs(x - curr[0]) < 5 and abs(y - curr[1]) < 5:
      return True
  return False

def getCorners(frame,last_aspectRatio):
  n_detected = 0
  corners = np.empty([0, 2], dtype=np.float32)
  moments = np.empty([0, 2], dtype=np.float32)
  current_corners = np.empty([0, 2], dtype=np.float32)

  detected_corners = False
  status = "No Targets"

  # convert the frame to grayscale, blur it, and detect edges
  gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
  blurred = cv2.GaussianBlur(gray, (7, 7), 3)
  edged = cv2.Canny(blurred, 1, 100)

  kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
  edged = cv2.dilate(edged, kernel) # Also try 
  #edged = cv2.morphologyEx(edged, cv2.MORPH_CLOSE, kernel)
  cv2.imshow("edged",edged)

  # find contours in the edge map
  cnts = cv2.findContours(edged, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
  cnts = imutils.grab_contours(cnts)

  # loop over the contours
  for c in cnts:
    # approximate the contour
    peri = cv2.arcLength(c, True)
    approx = cv2.approxPolyDP(c, 0.1 * peri, True)
    approx = cv2.convexHull(approx)
    #cv2.drawContours(frame, [approx], 0, (0, 255, 0), 1)

    # ensure that the approximated contour is "roughly" rectangular
    if len(approx) == 4:
      # compute the bounding box of the approximated contour and
      # use the bounding box to compute the aspect ratio
      (x, y, w, h) = cv2.boundingRect(approx)
      aspectRatio = w / float(h)

      # compute the solidity of the original contour
      area = cv2.contourArea(c)
      hullArea = cv2.contourArea(cv2.convexHull(c))
      solidity = area / float(hullArea)

      # compute whether or not the width and height, solidity, and
      # aspect ratio of the contour falls within appropriate bounds
      keepDims = w > 25 and h > 25
      keepSolidity = solidity > 0.9
      keepAspectRatio = aspectRatio >= 1.4 and aspectRatio <= 1.8
      #keepDims, keepAspectRatio, keepAspectRatio = True,True,True
      #keepAspectRatio = True

      detected = keepDims and keepSolidity and keepAspectRatio
      #detected = True

      # ensure that the contour passes all our tests
      if detected and not cornerIn([x, y], current_corners):
        detected_corners = True
        n_detected += 1
        current_corners = np.append(current_corners, np.array([[x, y]]), axis=0)
        approx = np.squeeze(approx, axis = 1)
        #print("approx: ", np.shape(approx), " corners: ", np.shape(corners))
        corners = np.vstack([corners, approx])

        # draw an outline around the target and update the status text
        cv2.drawContours(frame, [approx], -1, (0, 0, 255), 3)
        last_aspectRatio = aspectRatio
        status = "Target(s) Acquired"
        # compute the center of the contour region and draw the crosshairs
        M = cv2.moments(approx)
        (cX, cY) = (int(M["m10"] / (M["m00"] + 1e-7)), int(M["m01"] / (M["m00"] + 1e-7)))
        moments = np.vstack([moments, [cX, cY]])
        cv2.circle(frame, (cX, cY), 5, (0, 0, 255), thickness=-1, lineType=8, shift=0)

  # draw the status text on the frame
  cv2.putText(frame,status + " - Aspect Ratio: " + str('%0.3f' % last_aspectRatio) + " - n_detected: " + str(n_detected), (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
  return frame, detected_corners, corners, moments, last_aspectRatio

def estimateCameraPose(objp, corners, mtx, dist):

  pos = 0

  try:
    ret, rvec, tvec = cv2.solvePnP(objp, corners, mtx, dist)
    tvec = np.squeeze(tvec)

    if ret:
      Rt,jacob = cv2.Rodrigues(rvec)
      R = Rt.transpose()
      #print("R",Rt)
      pos = tvec.dot(-Rt)
      print("Distance: ",np.linalg.norm(pos))
      print("pos",pos)
  except:
    warnings.warn("Error is estimateCameraPose")
    print("\n objp:", objp,
        "\n corners:", corners,
        "\n mtx:", mtx,
        "\n dst:", dist,)

  return pos

def createRectWorldPoints(w1, h1, w2, h2, dw, dh):
  worldPnts = np.zeros((8,3), dtype=np.float32)

  worldPnts[0] = np.array([0,0,0])
  worldPnts[1] = np.array([0,h1,0])
  worldPnts[2] = np.array([w1,0,0])
  worldPnts[3] = np.array([w1,h1,0])

  worldPnts[4] = np.array([dw,dh,0])
  worldPnts[5] = np.array([dw,dh+h2,0])
  worldPnts[6] = np.array([dw+w2,dh,0])
  worldPnts[7] = np.array([dw+w2,dh+h2,0])

  return worldPnts

def trackRect(frame,x,y,w,h): #We can probably change this function to pass roi directly
  track_window = (x, y, w, h)
  roi = frame[y:y + h, x:x + w]
  hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
  mask = cv2.inRange(hsv_roi, np.array((0., 0., 0.)), np.array((255., 255., 255.)))
  roi_hist = cv2.calcHist([hsv_roi], [0], mask, [180], [0, 180])
  cv2.normalize(roi_hist, roi_hist, 0, 255, cv2.NORM_MINMAX)

  hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)  #This could probably be calculated somewhere else
  dst = cv2.calcBackProject([hsv], [0], roi_hist, [0, 180], 1)

  # apply CamShift to get the new location
  ret, track_window = cv2.CamShift(dst, track_window, (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10,1))

  # Draw it on image
  x, y, w, h = track_window
  img2 = cv2.rectangle(frame, (x, y), (x + w, y + h), 255, 2)
  cv2.imshow('img2', img2)
  return x,y,w,h

def sortCorners(corners):
  if corners.shape[0] == 8:
    corners = corners[corners[:,0].argsort()]

    corners[0:2] = corners[corners[0:2,1].argsort()]
    corners[2:4] = corners[2+corners[2:4,1].argsort()]
    corners[4:6] = corners[4+corners[4:6,1].argsort()]
    corners[6:8] = corners[6+corners[6:8,1].argsort()]

    corners = np.insert(corners, 2, np.array([corners[-2], corners[-1]]), axis=0)
    corners = np.delete(corners, [8, 9], axis=0)

    return corners
  else:
    return corners

def checkCentroids(corners, moments):

  if len(corners) > 8:
    corners_out = np.empty([0, 2], dtype=np.float32)

    norm_thresh = 10

    for i in range(len(moments)):
      keep = False
      keep_j = 0

      for j in range(i+1, len(moments)):
        dist = np.linalg.norm(moments[i,:] - moments[j,:])
        print('moments distance: ', dist)
        if dist < norm_thresh:
          keep = True
          keep_j = j

      if keep:
        corners_out = np.vstack([corners_out, corners[4*i:4*i+4,:]])
        corners_out = np.vstack([corners_out, corners[4*keep_j:4*keep_j+4,:]])

    if corners_out.shape[0] == 0:
      print('Centroid Check Failed, corners_out is empty')
      return corners
    else:
      return corners_out

  else:
    return corners

def labelCorners(corners,frame):
  counter = 0
  for x, y in corners:
    counter += 1
    cv2.circle(frame, (int(x), int(y)), 5, (0, 255, 255), thickness=-1, lineType=8, shift=0)
    cv2.putText(frame, str(counter), (int(x + 12), int(y + 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
          (0, 255, 255), 2)


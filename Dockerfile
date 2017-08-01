FROM scannerresearch/scanner:cpu
ARG project
ARG zone

# Install Ubuntu packages
RUN apt-get update && apt-get install -y curl
RUN export CLOUD_SDK_REPO="cloud-sdk-$(lsb_release -c -s)" && \
    echo "deb http://packages.cloud.google.com/apt $CLOUD_SDK_REPO main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add - && \
    apt-get update && apt-get install -y google-cloud-sdk kubectl

# TODO(wcrichto): is there a way to mount .:/app during build to avoid the ADDs here?
WORKDIR /app

# Install python dependencies
ADD requirements.txt .
RUN pip install -r requirements.txt

# Authenticate with gcloud and configure project settings
ADD google-key.json .
RUN gcloud auth activate-service-account --key-file=google-key.json && \
    gcloud config set project ${project} && \
    gcloud config set compute/zone ${zone}
ENV GOOGLE_APPLICATION_CREDENTIALS=/app/google-key.json

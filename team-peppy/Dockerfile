# The existing, pinned DSH image on the Huly host supplies Harness and its locked dependencies.
ARG DSH_BASE_IMAGE=pop-super-agent:8c32a9d
FROM ${DSH_BASE_IMAGE}
USER root
WORKDIR /opt/pop-super-agent
RUN rm -rf ./lib ./team-peppy-ui
COPY lib/ ./lib/
COPY team-peppy-ui/ ./team-peppy-ui/
COPY package.json cordis.patch.yml ./
USER node
WORKDIR /workspace

function update () {
	brew update
	brew outdated
	brew outdated --cask
	brew upgrade
	brew cleanup
	mas upgrade
	softwareupdate -i -a
}
